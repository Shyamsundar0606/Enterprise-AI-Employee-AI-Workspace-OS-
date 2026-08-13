from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.llm.config import get_provider_name
from app.llm.schemas import (
    LLMChatRequest,
    LLMChatResponse,
    LLMHealthResponse,
    LLMModelsResponse,
)
from app.llm.service import LLMService

router = APIRouter(tags=["llm"])


def get_llm_service() -> LLMService:
    return LLMService()


@router.get("/llm/health", response_model=LLMHealthResponse)
async def llm_health(service: Annotated[LLMService, Depends(get_llm_service)]) -> LLMHealthResponse:
    return await service.health()


@router.get("/llm/models", response_model=LLMModelsResponse)
async def llm_models(service: Annotated[LLMService, Depends(get_llm_service)]) -> LLMModelsResponse:
    models = await service.list_models()
    return LLMModelsResponse(provider=get_provider_name().lower(), models=models)


@router.post("/llm/chat", response_model=LLMChatResponse)
async def llm_chat(
    payload: LLMChatRequest, service: Annotated[LLMService, Depends(get_llm_service)]
) -> LLMChatResponse:
    response = await service.chat(payload)
    if isinstance(response, dict):
        return LLMChatResponse(
            conversation_id=response.get("conversation_id", payload.conversation_id),
            response=response.get("response", ""),
            provider=response.get("provider", payload.provider),
            model=response.get("model", payload.model),
            latency_ms=response.get("latency_ms"),
        )
    return LLMChatResponse(
        conversation_id=response.conversation_id,
        response=response.response,
        provider=response.provider,
        model=response.model,
        latency_ms=response.latency_ms,
    )


@router.post("/llm/stream")
async def llm_stream(
    payload: LLMChatRequest, service: Annotated[LLMService, Depends(get_llm_service)]
) -> StreamingResponse:
    async def event_stream():
        async for payload_chunk in service.stream(payload):
            yield f"data: {payload_chunk['chunk']}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
