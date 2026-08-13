from __future__ import annotations

import logging
import time

from app.llm.exceptions import LLMError
from app.llm.providers.base import BaseLLMProvider
from app.llm.schemas import LLMChatRequest, LLMChatResponse, LLMHealthResponse, LLMModelInfo

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self, provider: BaseLLMProvider | None = None) -> None:
        self.provider = provider

    async def chat(self, request: LLMChatRequest) -> LLMChatResponse:
        start = time.perf_counter()
        provider = self.provider or self._get_provider()
        provider_name = getattr(provider, "name", request.provider or "ollama")
        provider_model = request.model or getattr(provider, "default_model", "qwen3")
        try:
            response_text = await provider.generate(
                prompt=request.message,
                model=provider_model,
                temperature=request.temperature if request.temperature is not None else 0.7,
                max_tokens=request.max_tokens if request.max_tokens is not None else 512,
                timeout=30.0,
            )
        except LLMError as exc:
            logger.exception(
                "LLM request failed",
                extra={"provider": provider_name, "conversation_id": request.conversation_id},
            )
            raise exc

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "LLM request completed",
            extra={
                "provider": provider_name,
                "model": provider_model,
                "conversation_id": request.conversation_id,
                "duration_ms": latency_ms,
                "token_count": len(response_text.split()),
            },
        )
        return LLMChatResponse(
            conversation_id=request.conversation_id,
            response=response_text,
            provider=provider_name,
            model=provider_model,
            latency_ms=latency_ms,
        )

    async def stream(self, request: LLMChatRequest):
        provider = self.provider or self._get_provider()
        async for chunk in provider.stream(
            prompt=request.message,
            model=request.model or "qwen3",
            temperature=request.temperature if request.temperature is not None else 0.7,
            max_tokens=request.max_tokens if request.max_tokens is not None else 512,
            timeout=30.0,
        ):
            yield {"chunk": chunk}

    async def list_models(self) -> list[LLMModelInfo]:
        provider = self.provider or self._get_provider()
        return await provider.list_models()

    async def health(self) -> LLMHealthResponse:
        provider = self.provider or self._get_provider()
        return await provider.health()

    def _get_provider(self) -> BaseLLMProvider:
        from app.llm.factory import ProviderFactory

        return ProviderFactory.create_provider()
