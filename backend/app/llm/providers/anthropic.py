from __future__ import annotations

from app.llm.exceptions import ProviderAuthError
from app.llm.providers.base import BaseLLMProvider
from app.llm.schemas import LLMHealthResponse, LLMModelInfo


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    async def generate(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int, timeout: float
    ) -> str:
        raise ProviderAuthError(
            "Anthropic provider is not configured. Add an API key to enable it."
        )

    async def stream(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int, timeout: float
    ):
        raise ProviderAuthError(
            "Anthropic provider is not configured. Add an API key to enable it."
        )

    async def list_models(self) -> list[LLMModelInfo]:
        return []

    async def health(self) -> LLMHealthResponse:
        return LLMHealthResponse(
            provider=self.name,
            model="",
            status="error",
            latency_ms=None,
            detail="Anthropic provider requires credentials",
        )

    async def embeddings(self, *, text: str, model: str, timeout: float) -> list[float]:
        raise ProviderAuthError(
            "Anthropic provider is not configured. Add an API key to enable it."
        )
