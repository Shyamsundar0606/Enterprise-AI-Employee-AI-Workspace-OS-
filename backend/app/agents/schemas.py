from pydantic import BaseModel, Field


class AgentPlan(BaseModel):
    goal: str
    steps: list[str]
    requires_tools: bool = False


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


class AgentInfo(BaseModel):
    name: str
    description: str


class AgentHealthResponse(BaseModel):
    status: str
    agent: str
    provider: str
    detail: str | None = None
