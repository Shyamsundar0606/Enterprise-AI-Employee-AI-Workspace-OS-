from __future__ import annotations

from app.llm.config import get_provider_name
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.openai import OpenAIProvider


class ProviderFactory:
    @staticmethod
    def create_provider() -> BaseLLMProvider:
        provider_name = get_provider_name()
        providers = {
            "OLLAMA": OllamaProvider,
            "OPENAI": OpenAIProvider,
            "GEMINI": GeminiProvider,
        }
        provider_cls = providers.get(provider_name)
        if provider_cls is None:
            raise ValueError(f"Unsupported LLM provider: {provider_name}")
        return provider_cls()
