import asyncio
import base64
import os
import re
from typing import AsyncIterator

AUDIO_DELAY_MS = int(os.getenv("AUDIO_DELAY_MS", "80"))
SENTENCE_MAX_DELAY_MS = int(os.getenv("SENTENCE_MAX_DELAY_MS", "500"))

async def sentence_buffer(tokens: AsyncIterator[str]) -> AsyncIterator[str]:
    """Sammelt Tokens bis zum Satzende.

    TODO Übung 4:
    - Bei Satzzeichen .!? flushen.
    - Zusätzlich nach SENTENCE_MAX_DELAY_MS flushen, auch ohne Satzende.
    - Leere Chunks vermeiden.
    """
    buf = ""
    async for token in tokens:
        buf += token
        if re.search(r"[.!?]\s*$", buf):
            yield buf.strip()
            buf = ""
    if buf.strip():
        yield buf.strip()

async def tts_mock(sentence: str) -> AsyncIterator[bytes]:
    """Deterministische Audio-Simulation: liefert Bytes statt echter WAV/MP3."""
    payload = ("AUDIO:" + sentence).encode("utf-8")
    for i in range(0, len(payload), 32):
        await asyncio.sleep(AUDIO_DELAY_MS / 1000)
        yield payload[i:i+32]

def audio_event(chunk: bytes) -> str:
    # SSE-safe: Binärdaten als base64 transportieren.
    return "data: " + base64.b64encode(chunk).decode("ascii") + "\n\n"
