"""Validated contracts for enterprise connector execution."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AccessType(StrEnum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class ConnectorContext(BaseModel):
    """Trusted context built only from the authenticated request."""

    model_config = ConfigDict(frozen=True)

    authenticated_user_id: int = Field(gt=0)
    role: str = Field(min_length=1, max_length=32)
    conversation_id: str | None = Field(default=None, max_length=64)
    request_id: str | None = Field(default=None, max_length=128)


class ConnectorCapability(BaseModel):
    name: str
    description: str
    access_type: AccessType
    input_schema: dict[str, Any]


class EmptyInput(BaseModel):
    """Explicit schema for operations that accept no arguments."""


class ConnectorRequest(BaseModel):
    connector_id: str = Field(pattern="^[a-z][a-z0-9_]{0,63}$")
    operation: str = Field(pattern="^[a-z][a-z0-9_]{0,63}$")
    arguments: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = Field(default=None, max_length=64)


class ConnectorErrorDetail(BaseModel):
    code: str
    message: str


class ConnectorResult(BaseModel):
    connector_id: str
    operation: str
    status: Literal["success", "error", "approval_required"]
    data: dict[str, Any] | None = None
    error: ConnectorErrorDetail | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False


class ConnectorInfo(BaseModel):
    id: str
    name: str
    description: str
    capabilities: list[ConnectorCapability]
    requires_credentials: bool
    enabled: bool
