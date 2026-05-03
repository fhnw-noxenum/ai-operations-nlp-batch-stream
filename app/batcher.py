import asyncio
import os
from dataclasses import dataclass
from typing import List

from prometheus_client import Histogram

from app.model import model

BATCH_WINDOW_MS = int(os.getenv("BATCH_WINDOW_MS", "15"))
MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "8"))
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "128"))

MICROBATCH_SIZE = Histogram("llm_microbatch_size", "Observed microbatch size")


@dataclass
class BatchItem:
    prompt: str
    max_tokens: int
    future: asyncio.Future


class MicroBatcher:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[BatchItem] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._worker: asyncio.Task | None = None

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run())

    async def submit(self, prompt: str, max_tokens: int) -> str:
        self.start()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        await self.queue.put(
            BatchItem(prompt=prompt, max_tokens=max_tokens, future=fut)
        )
        return await fut

    async def _collect(self, first: BatchItem) -> List[BatchItem]:
        batch = [first]
        deadline = asyncio.get_running_loop().time() + BATCH_WINDOW_MS / 1000
        while len(batch) < MAX_BATCH_SIZE:
            timeout = deadline - asyncio.get_running_loop().time()
            if timeout <= 0:
                break
            try:
                batch.append(await asyncio.wait_for(self.queue.get(), timeout=timeout))
            except asyncio.TimeoutError:
                break
        return batch

    async def _run(self) -> None:
        while True:
            first = await self.queue.get()
            batch = await self._collect(first)
            try:
                MICROBATCH_SIZE.observe(len(batch))
                max_tokens = max(item.max_tokens for item in batch)
                results = await model.generate_batch(
                    [item.prompt for item in batch], max_tokens=max_tokens
                )
                for item, result in zip(batch, results):
                    if not item.future.done():
                        item.future.set_result(result)
            except Exception as exc:
                for item in batch:
                    if not item.future.done():
                        item.future.set_exception(exc)


batcher = MicroBatcher()
