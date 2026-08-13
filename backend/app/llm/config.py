from __future__ import annotations

import os
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    llm_provider: Literal["OLLAMA", "OPENAI", "GEMINI"] = Field(default="OLLAMA")
    ollama_url: str = Field(default="http://host.docker.internal:11434")
    default_model: str = Field(default="qwen3")
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=512)
    request_timeout: float = Field(default=30.0)
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: SecretStr | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"


def get_llm_settings() -> LLMSettings:
    return LLMSettings()


def get_provider_name() -> str:
    return os.getenv("LLM_PROVIDER", "OLLAMA").upper()
