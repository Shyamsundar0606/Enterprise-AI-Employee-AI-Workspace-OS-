from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agents.registry import AgentRegistry
from app.agents.runtime import AgentRuntime
from app.agents.schemas import AgentChatRequest, AgentChatResponse, AgentHealthResponse, AgentInfo
from app.auth.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/agents", tags=["agents"])


def get_agent_runtime() -> AgentRuntime:
    return AgentRuntime()


def get_agent_registry() -> AgentRegistry:
    return AgentRegistry()


@router.get("/health", response_model=AgentHealthResponse)
async def health(
    runtime: Annotated[AgentRuntime, Depends(get_agent_runtime)],
    _: Annotated[User, Depends(get_current_user)],
) -> AgentHealthResponse:
    return await runtime.health()


@router.get("/list", response_model=list[AgentInfo])
async def list_agents(
    registry: Annotated[AgentRegistry, Depends(get_agent_registry)],
    _: Annotated[User, Depends(get_current_user)],
) -> list[AgentInfo]:
    return [
        AgentInfo(
            name=agent.name,
            description=agent.description,
            capabilities=list(agent.capabilities),
            enabled=agent.enabled,
        )
        for agent in registry.list()
    ]


@router.post("/chat", response_model=AgentChatResponse)
async def chat(
    payload: AgentChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    runtime: Annotated[AgentRuntime, Depends(get_agent_runtime)],
) -> AgentChatResponse:
    return await runtime.run(
        user_id=current_user.id,
        user_role=current_user.role,
        request=payload,
    )


@router.post("/stream")
async def stream(
    payload: AgentChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    runtime: Annotated[AgentRuntime, Depends(get_agent_runtime)],
) -> StreamingResponse:
    async def events():
        async for chunk in runtime.stream(user_id=current_user.id, request=payload):
            yield f"data: {chunk}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
