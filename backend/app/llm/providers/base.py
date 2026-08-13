from __future__ import annotations

from abc import ABC, abstractmethod

from app.llm.schemas import LLMHealthResponse, LLMModelInfo


class BaseLLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def generate(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int, timeout: float
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int, timeout: float
    ):
        raise NotImplementedError

    @abstractmethod
    async def list_models(self) -> list[LLMModelInfo]:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> LLMHealthResponse:
        raise NotImplementedError

    @abstractmethod
    async def embeddings(self, *, text: str, model: str, timeout: float) -> list[float]:
        raise NotImplementedError
