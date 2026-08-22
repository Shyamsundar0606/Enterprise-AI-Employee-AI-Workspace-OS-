"""Safe HTTP contracts for user-owned workflows."""

from typing import Any

from pydantic import BaseModel, Field


class WorkflowStepCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    step_type: str = Field(pattern="^(connector|tool|knowledge)$")
    connector_id: str | None = None
    operation: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[int] = Field(default_factory=list)
    access_type: str | None = None
    requires_approval: bool = False
    max_retries: int | None = Field(default=None, ge=0)


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    steps: list[WorkflowStepCreate] = Field(min_length=1, max_length=20)


class WorkflowOut(BaseModel):
    id: str
    name: str
    status: str
    current_step: int


class WorkflowStepOut(BaseModel):
    id: str
    position: int
    name: str
    step_type: str
    status: str
    result: dict[str, Any] | None
