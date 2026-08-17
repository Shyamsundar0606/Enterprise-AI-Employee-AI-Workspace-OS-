"""Contracts shared by registered tools and the agent runtime."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolContext(BaseModel):
    """Trusted execution context derived from the authenticated user."""

    model_config = ConfigDict(frozen=True)

    user_id: int = Field(gt=0)
    role: str = Field(min_length=1, max_length=32)
    conversation_id: str = Field(min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolErrorDetail(BaseModel):
    code: str
    message: str


class ToolResult(BaseModel):
    """Safe, serializable result returned for every attempted tool execution."""

    tool_name: str
    status: Literal["success", "error"]
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    error: ToolErrorDetail | None = None


class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
