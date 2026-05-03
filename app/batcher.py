import asyncio
import os
from dataclasses import dataclass
from typing import List

from app.model import model

BATCH_WINDOW_MS = int(os.getenv("BATCH_WINDOW_MS", "15"))
MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "8"))
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "128"))

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
        await self.queue.put(BatchItem(prompt=prompt, max_tokens=max_tokens, future=fut))
        return await fut

    async def _run(self) -> None:
        while True:
            first = await self.queue.get()

            # TODO Übung 2:
            # 1. Sammle weitere Requests bis MAX_BATCH_SIZE erreicht ist
            #    oder BATCH_WINDOW_MS abgelaufen ist.
            # 2. Rufe model.generate_batch(prompts, max_tokens=...) einmal auf.
            # 3. Setze jedes Ergebnis auf das passende Future.
            # 4. Propagiere Exceptions auf alle Futures.
            batch: List[BatchItem] = [first]
            result = await model.generate(first.prompt, max_tokens=first.max_tokens)
            first.future.set_result(result)

batcher = MicroBatcher()
