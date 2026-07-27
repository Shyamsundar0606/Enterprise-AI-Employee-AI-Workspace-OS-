from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    is_archived: bool | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: int
    title: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationOut]
    total: int
    page: int
    page_size: int


class MessageCreate(BaseModel):
    conversation_id: str
    role: str = Field(pattern="^(user|assistant|system|tool)$")
    content: str = Field(min_length=1)
    metadata: dict[str, Any] | None = None
    token_count: int | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: str
    metadata: dict[str, Any] | None
    token_count: int | None
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageOut]
    total: int
    page: int
    page_size: int


class DeleteResponse(BaseModel):
    deleted: bool
    id: str
