"""Small local LLM backend for the Batch & Stream Inference Lab.

This replaces the previous deterministic MockLLM with a real Hugging Face
Transformers causal language model that runs locally in the API container.

Defaults are chosen for CPU-only classroom laptops. Override MODEL_ID in
`docker-compose.yml` or via environment variable if you want a different model.
"""

from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import dataclass
from typing import AsyncIterator, Iterable, List, Optional

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer


@dataclass(frozen=True)
class ModelConfig:
    # Good default for local classroom testing. First run downloads the model once
    # into the mounted Hugging Face cache volume.
    model_id: str = os.getenv("MODEL_ID", "HuggingFaceTB/SmolLM2-135M-Instruct")
    device: str = os.getenv("MODEL_DEVICE", "cpu")
    dtype: str = os.getenv("MODEL_DTYPE", "float32")
    max_input_tokens: int = int(os.getenv("MAX_INPUT_TOKENS", "512"))
    do_sample: bool = os.getenv("DO_SAMPLE", "false").lower() == "true"
    temperature: float = float(os.getenv("TEMPERATURE", "0.7"))
    top_p: float = float(os.getenv("TOP_P", "0.9"))
    timeout_seconds: float = float(os.getenv("GENERATION_TIMEOUT_SECONDS", "120"))


def _next_or_none(iterator):
    """Return next(iterator), or None at stream end.

    A helper is used because raising StopIteration through asyncio.to_thread()
    can produce awkward Future/Task behaviour in some Python versions.
    """
    try:
        return next(iterator)
    except StopIteration:
        return None


class LocalTransformersLLM:
    """Tiny local LLM wrapper with sync, streaming and batch interfaces.

    Methods are async because the FastAPI app is async. Actual model work is run
    in a worker thread so the event loop is not blocked.
    """

    def __init__(self, config: Optional[ModelConfig] = None) -> None:
        self.config = config or ModelConfig()
        self._tokenizer = None
        self._model = None
        self._load_lock = threading.Lock()
        self._generate_lock = threading.Lock()

        # Keep CPU use predictable when students run Docker Desktop locally.
        torch_threads = int(os.getenv("TORCH_NUM_THREADS", "2"))
        torch.set_num_threads(max(1, torch_threads))

    def _torch_dtype(self):
        if self.config.dtype in {"float16", "fp16"}:
            return torch.float16
        if self.config.dtype in {"bfloat16", "bf16"}:
            return torch.bfloat16
        return torch.float32

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return

        with self._load_lock:
            if self._model is not None and self._tokenizer is not None:
                return

            tokenizer = AutoTokenizer.from_pretrained(self.config.model_id)
            tokenizer.padding_side = "left"
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            model = AutoModelForCausalLM.from_pretrained(
                self.config.model_id,
                torch_dtype=self._torch_dtype(),
                low_cpu_mem_usage=True,
            )
            model.to(self.config.device)
            model.eval()

            self._tokenizer = tokenizer
            self._model = model

    def _format_prompt(self, prompt: str) -> str:
        self._ensure_loaded()
        assert self._tokenizer is not None

        # Instruct models get a chat prompt. Tiny GPT-style models fall back to a
        # plain instruction format.
        if getattr(self._tokenizer, "chat_template", None):
            messages = [
                {
                    "role": "system",
                    "content": "Du antwortest knapp und hilfreich für einen AI-Operations Unterricht.",
                },
                {"role": "user", "content": prompt},
            ]
            return self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )

        return (
            "Du bist ein knapper hilfreicher Assistent für AI Operations.\n"
            f"User: {prompt}\n"
            "Assistant:"
        )

    def _generation_kwargs(self, max_tokens: int) -> dict:
        self._ensure_loaded()
        assert self._tokenizer is not None

        kwargs = {
            "max_new_tokens": max_tokens,
            "do_sample": self.config.do_sample,
            "pad_token_id": self._tokenizer.pad_token_id,
            "eos_token_id": self._tokenizer.eos_token_id,
        }
        if self.config.do_sample:
            kwargs.update({"temperature": self.config.temperature, "top_p": self.config.top_p})
        return kwargs

    def _encode(self, prompts: List[str]) -> dict:
        self._ensure_loaded()
        assert self._tokenizer is not None

        formatted = [self._format_prompt(p) for p in prompts]
        encoded = self._tokenizer(
            formatted,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.config.max_input_tokens,
        )
        return {key: value.to(self.config.device) for key, value in encoded.items()}

    def _generate_batch_sync(self, prompts: List[str], max_tokens: int) -> List[str]:
        self._ensure_loaded()
        assert self._model is not None
        assert self._tokenizer is not None

        encoded = self._encode(prompts)
        input_width = encoded["input_ids"].shape[1]

        with self._generate_lock, torch.inference_mode():
            output_ids = self._model.generate(
                **encoded,
                **self._generation_kwargs(max_tokens),
            )

        generated_ids = output_ids[:, input_width:]
        decoded = self._tokenizer.batch_decode(generated_ids, skip_special_tokens=True)
        return [text.strip() for text in decoded]

    async def generate(self, prompt: str, max_tokens: int = 80) -> str:
        results = await self.generate_batch([prompt], max_tokens=max_tokens)
        return results[0]

    async def generate_batch(self, prompts: Iterable[str], max_tokens: int = 80) -> List[str]:
        prompt_list = list(prompts)
        if not prompt_list:
            return []
        return await asyncio.to_thread(self._generate_batch_sync, prompt_list, max_tokens)

    async def stream(self, prompt: str, max_tokens: int = 80) -> AsyncIterator[str]:
        """Stream decoded text chunks from a real model via TextIteratorStreamer."""
        self._ensure_loaded()
        assert self._model is not None
        assert self._tokenizer is not None

        encoded = self._encode([prompt])
        streamer = TextIteratorStreamer(
            self._tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
            timeout=self.config.timeout_seconds,
        )

        generation_kwargs = {
            **encoded,
            **self._generation_kwargs(max_tokens),
            "streamer": streamer,
        }

        def run_generation() -> None:
            try:
                with self._generate_lock, torch.inference_mode():
                    self._model.generate(**generation_kwargs)
            except Exception as exc:  # make failures visible to the SSE client
                streamer.on_finalized_text(f"\n[GENERATION_ERROR: {exc}]", stream_end=True)

        thread = threading.Thread(target=run_generation, daemon=True)
        thread.start()

        iterator = iter(streamer)
        while True:
            chunk = await asyncio.to_thread(_next_or_none, iterator)
            if chunk is None:
                break
            if chunk:
                yield chunk

        thread.join(timeout=1)


model = LocalTransformersLLM()
