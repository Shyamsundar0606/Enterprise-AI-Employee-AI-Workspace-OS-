"""Local embedding abstraction backed by the existing Ollama provider."""

from __future__ import annotations

import math
from typing import Protocol

from app.config.settings import get_settings
from app.llm.providers.ollama import OllamaProvider


class EmbeddingError(RuntimeError):
    """Raised when an embedding cannot be generated or validated."""


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class OllamaEmbeddingProvider:
    """Uses the local Ollama HTTP provider without coupling callers to its internals."""

    def __init__(self, provider: OllamaProvider | None = None) -> None:
        settings = get_settings()
        self._provider = provider or OllamaProvider(base_url=settings.embedding_base_url)
        self._settings = settings

    async def embed(self, text: str) -> list[float]:
        return await self._provider.embeddings(
            text=text,
            model=self._settings.embedding_model,
            timeout=self._settings.embedding_timeout,
        )


class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self._provider = provider or OllamaEmbeddingProvider()

    async def embed(self, text: str) -> list[float]:
        try:
            embedding = await self._provider.embed(text)
        except Exception as exc:
            raise EmbeddingError("Embedding provider is unavailable") from exc
        self._validate(embedding)
        return embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = [await self.embed(text) for text in texts]
        if vectors and any(len(vector) != len(vectors[0]) for vector in vectors):
            raise EmbeddingError("Embedding vectors have inconsistent dimensions")
        return vectors

    @staticmethod
    def _validate(embedding: list[float]) -> None:
        if not embedding or any(not isinstance(value, int | float) for value in embedding):
            raise EmbeddingError("Embedding provider returned an invalid vector")
        if any(not math.isfinite(float(value)) for value in embedding):
            raise EmbeddingError("Embedding vector must contain finite values")
