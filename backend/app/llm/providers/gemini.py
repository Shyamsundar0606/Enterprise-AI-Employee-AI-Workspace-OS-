from __future__ import annotations

import httpx

from app.llm.config import get_llm_settings
from app.llm.exceptions import ProviderAuthError, ProviderUnavailableError
from app.llm.providers.base import BaseLLMProvider
from app.llm.schemas import LLMHealthResponse, LLMModelInfo


class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    def _credentials(self) -> tuple[str, str]:
        settings = get_llm_settings()
        if settings.gemini_api_key is None:
            raise ProviderAuthError("Gemini is not configured. Set GEMINI_API_KEY to enable it.")
        return settings.gemini_api_key.get_secret_value(), settings.gemini_base_url.rstrip("/")

    async def generate(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int, timeout: float
    ) -> str:
        key, base_url = self._credentials()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url}/models/{model}:generateContent",
                    params={"key": key},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": temperature,
                            "maxOutputTokens": max_tokens,
                        },
                    },
                )
                response.raise_for_status()
                return str(response.json()["candidates"][0]["content"]["parts"][0]["text"])
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Gemini request failed: {exc}") from exc

    async def stream(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int, timeout: float
    ):
        yield await self.generate(
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    async def list_models(self) -> list[LLMModelInfo]:
        self._credentials()
        return []

    async def health(self) -> LLMHealthResponse:
        try:
            self._credentials()
        except ProviderAuthError as exc:
            return LLMHealthResponse(provider=self.name, model="", status="error", detail=str(exc))
        return LLMHealthResponse(
            provider=self.name, model="", status="degraded", detail="Credentials configured"
        )

    async def embeddings(self, *, text: str, model: str, timeout: float) -> list[float]:
        key, base_url = self._credentials()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url}/models/{model}:embedContent",
                    params={"key": key},
                    json={"content": {"parts": [{"text": text}]}},
                )
                response.raise_for_status()
                return list(response.json()["embedding"]["values"])
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Gemini embedding request failed: {exc}") from exc
