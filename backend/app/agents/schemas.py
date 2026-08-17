from typing import Any

from pydantic import BaseModel, Field

from app.schemas.knowledge import KnowledgeSource
from app.tools.schemas import ToolResult


class AgentPlan(BaseModel):
    goal: str
    steps: list[str]
    requires_tools: bool = False
    tool_name: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)


class AgentTask(BaseModel):
    task_id: str
    agent_name: str = Field(pattern="^(general|knowledge|data|planner|integration)$")
    instruction: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=list)
    parent_task_id: str | None = None
    depth: int = Field(default=0, ge=0, le=8)


class AgentResult(BaseModel):
    task_id: str
    agent_name: str
    status: str
    content: str = ""
    sources: list[KnowledgeSource] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    agents_used: list[str] = Field(default_factory=list)
    delegation_count: int = 0


class AgentInfo(BaseModel):
    name: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True


class AgentHealthResponse(BaseModel):
    status: str
    agent: str
    provider: str
    detail: str | None = None
