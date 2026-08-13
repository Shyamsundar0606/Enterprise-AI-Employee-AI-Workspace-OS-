from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LLMChatRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    provider: str = "ollama"
    model: str = "qwen3"
    temperature: float | None = None
    max_tokens: int | None = None


class LLMChatResponse(BaseModel):
    conversation_id: str
    response: str
    provider: str
    model: str
    latency_ms: float | None = None


class LLMHealthResponse(BaseModel):
    provider: str
    model: str
    status: Literal["ok", "degraded", "error"]
    latency_ms: float | None = None
    detail: str | None = None


class LLMModelInfo(BaseModel):
    name: str
    provider: str
    size: str | None = None
    details: str | None = None


class LLMModelsResponse(BaseModel):
    provider: str
    models: list[LLMModelInfo]
