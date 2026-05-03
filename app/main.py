import time
from typing import List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from pydantic import BaseModel, Field

from app.batcher import batcher
from app.model import model
from app.tts_mock import audio_event, sentence_buffer, tts_mock

app = FastAPI(title="Batch & Stream Inference Lab")

REQS = Counter("llm_requests_total", "LLM requests", ["endpoint"])
TOKENS = Counter("llm_tokens_total", "Output tokens", ["endpoint"])
LATENCY = Histogram("llm_request_seconds", "Request latency", ["endpoint"])
TTFT = Histogram("llm_ttft_seconds", "Time to first token/audio", ["endpoint"])
QUEUE_DEPTH = Gauge("llm_queue_depth", "Batch queue depth")
BATCH_SIZE = Histogram("llm_batch_size", "Observed batch size")


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    max_tokens: int = Field(80, ge=1, le=400)


class BatchRequest(BaseModel):
    prompts: List[str] = Field(..., min_length=1, max_length=64)
    max_tokens: int = Field(80, ge=1, le=400)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    QUEUE_DEPTH.set(batcher.queue.qsize())
    return PlainTextResponse(
        generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST
    )


@app.post("/v1/generate")
async def generate(req: GenerateRequest):
    REQS.labels("sync").inc()
    start = time.perf_counter()
    text = await model.generate(req.prompt, max_tokens=req.max_tokens)
    LATENCY.labels("sync").observe(time.perf_counter() - start)
    TOKENS.labels("sync").inc(len(text.split()))
    return {"text": text}


@app.post("/v1/batch")
async def batch(req: BatchRequest):
    REQS.labels("batch").inc(len(req.prompts))
    BATCH_SIZE.observe(len(req.prompts))
    start = time.perf_counter()
    # Starter: nutzt den MicroBatcher pro Request. Übung 2 verbessert dessen Scheduler.
    import asyncio

    results = await asyncio.gather(
        *(batcher.submit(p, req.max_tokens) for p in req.prompts)
    )
    LATENCY.labels("batch").observe(time.perf_counter() - start)
    TOKENS.labels("batch").inc(sum(len(r.split()) for r in results))
    return {"results": results}


@app.get("/v1/stream")
async def stream(prompt: str = Query(..., min_length=1), max_tokens: int = 80):
    REQS.labels("stream").inc()
    start = time.perf_counter()
    first = True

    async def events():
        nonlocal first
        async for token in model.stream(prompt, max_tokens=max_tokens):
            if first:
                TTFT.labels("stream").observe(time.perf_counter() - start)
                first = False
            TOKENS.labels("stream").inc(1)
            yield f"data: {token}\n\n"
        LATENCY.labels("stream").observe(time.perf_counter() - start)
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/v1/audio")
async def audio(prompt: str = Query(..., min_length=1), max_tokens: int = 80):
    REQS.labels("audio").inc()
    start = time.perf_counter()
    first = True

    async def events():
        nonlocal first
        # TODO Übung 4: sentence_buffer verbessern und Underrun-Metrik ergänzen.
        async for sentence in sentence_buffer(
            model.stream(prompt, max_tokens=max_tokens)
        ):
            async for chunk in tts_mock(sentence):
                if first:
                    TTFT.labels("audio").observe(time.perf_counter() - start)
                    first = False
                yield audio_event(chunk)
        LATENCY.labels("audio").observe(time.perf_counter() - start)
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
