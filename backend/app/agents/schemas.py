from typing import Any

from pydantic import BaseModel, Field

from app.tools.schemas import ToolResult
from app.schemas.knowledge import KnowledgeSource


class AgentPlan(BaseModel):
    goal: str
    steps: list[str]
    requires_tools: bool = False
    tool_name: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)


class AgentChatRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=20_000)


class AgentChatResponse(BaseModel):
    conversation_id: str
    response: str
    plan: AgentPlan
    provider: str
    status: str
    duration_ms: float
    tool_result: ToolResult | None = None
    sources: list[KnowledgeSource] = Field(default_factory=list)


class AgentInfo(BaseModel):
    name: str
    description: str


class AgentHealthResponse(BaseModel):
    status: str
    agent: str
    provider: str
    detail: str | None = None
