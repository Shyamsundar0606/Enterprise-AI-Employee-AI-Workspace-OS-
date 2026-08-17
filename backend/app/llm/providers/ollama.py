from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.llm.config import get_llm_settings
from app.llm.exceptions import ProviderConfigurationError, ProviderUnavailableError
from app.llm.providers.base import BaseLLMProvider
from app.llm.schemas import LLMHealthResponse, LLMModelInfo

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def __init__(self, *, base_url: str | None = None) -> None:
        settings = get_llm_settings()
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.timeout = settings.request_timeout
        self.default_model = settings.default_model

    async def _request(
        self, path: str, *, payload: dict[str, Any] | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        request_timeout = timeout or self.timeout
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=request_timeout) as client:
                    response = await client.post(
                        url, json=payload or {}, headers={"Content-Type": "application/json"}
                    )
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise ProviderUnavailableError(f"Ollama request failed: {exc}") from exc
                await asyncio.sleep(0.2 * (attempt + 1))
        raise ProviderUnavailableError("Ollama request failed")

    async def generate(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int, timeout: float
    ) -> str:
        payload = {
            "model": model or self.default_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        result = await self._request("/api/generate", payload=payload, timeout=timeout)
        return str(result.get("response", ""))

    async def stream(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int, timeout: float
    ):
        payload = {
            "model": model or self.default_model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/generate", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "response" in payload:
                        yield payload["response"]

    async def list_models(self) -> list[LLMModelInfo]:
        try:
            result = await self._request("/api/tags")
        except ProviderUnavailableError as exc:
            logger.warning("Ollama model listing unavailable: %s", exc)
            return [LLMModelInfo(name=self.default_model, provider=self.name)]

        models = result.get("models", [])
        return [
            LLMModelInfo(name=item.get("name", self.default_model), provider=self.name)
            for item in models
        ]

    async def health(self) -> LLMHealthResponse:
        try:
            result = await self._request("/api/tags", timeout=5.0)
            return LLMHealthResponse(
                provider=self.name,
                model=self.default_model,
                status="ok",
                latency_ms=10.0,
                detail=result.get("models", []) and "models available" or "no models",
            )
        except ProviderUnavailableError as exc:
            return LLMHealthResponse(
                provider=self.name,
                model=self.default_model,
                status="error",
                latency_ms=None,
                detail=str(exc),
            )

    async def embeddings(self, *, text: str, model: str, timeout: float) -> list[float]:
        if not text:
            raise ProviderConfigurationError("Text must not be empty")
        payload = {"model": model or self.default_model, "input": text}
        try:
            result = await self._request("/api/embed", payload=payload, timeout=timeout)
            embeddings = result.get("embeddings", [])
            if embeddings and isinstance(embeddings[0], list):
                return embeddings[0]
        except ProviderUnavailableError:
            pass
        result = await self._request("/api/embeddings", payload=payload, timeout=timeout)
        return result.get("embedding", [])
