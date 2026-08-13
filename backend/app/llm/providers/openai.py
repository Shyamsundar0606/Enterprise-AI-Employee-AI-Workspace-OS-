from __future__ import annotations

import httpx

from app.llm.config import get_llm_settings
from app.llm.exceptions import ProviderAuthError, ProviderUnavailableError
from app.llm.providers.base import BaseLLMProvider
from app.llm.schemas import LLMHealthResponse, LLMModelInfo


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def _credentials(self) -> tuple[str, str]:
        settings = get_llm_settings()
        if settings.openai_api_key is None:
            raise ProviderAuthError("OpenAI is not configured. Set OPENAI_API_KEY to enable it.")
        return settings.openai_api_key.get_secret_value(), settings.openai_base_url.rstrip("/")

    async def generate(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int, timeout: float
    ) -> str:
        key, base_url = self._credentials()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                response.raise_for_status()
                return str(response.json()["choices"][0]["message"]["content"])
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"OpenAI request failed: {exc}") from exc

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
                    f"{base_url}/embeddings",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": model, "input": text},
                )
                response.raise_for_status()
                return list(response.json()["data"][0]["embedding"])
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"OpenAI embedding request failed: {exc}") from exc
