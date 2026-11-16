"""Embedding provider port."""

from typing import Literal, Protocol

Purpose = Literal["document", "query"]


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    async def embed(self, texts: list[str], purpose: Purpose) -> list[list[float]]: ...
