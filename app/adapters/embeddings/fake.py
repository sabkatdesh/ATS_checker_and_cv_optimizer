"""Deterministic embeddings for tests and offline runs: no network, no randomness."""

import hashlib
import math
import struct

from app.ports.embeddings import Purpose
from app.ports.llm_errors import LLMBadRequest


class FakeEmbeddings:
    name = "fake"

    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions

    def _vector(self, text: str) -> list[float]:
        raw: list[float] = []
        counter = 0
        while len(raw) < self.dimensions:
            digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            raw.extend(v / 2**31 - 1.0 for v in struct.unpack(">8I", digest))
            counter += 1
        raw = raw[: self.dimensions]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    async def embed(self, texts: list[str], purpose: Purpose) -> list[list[float]]:
        """`purpose` never changes the vector."""
        if any(not t.strip() or len(t) > 50_000 for t in texts):
            raise LLMBadRequest("invalid text", provider=self.name)
        return [self._vector(t) for t in texts]
