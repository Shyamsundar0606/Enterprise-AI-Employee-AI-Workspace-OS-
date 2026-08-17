"""Transport schemas for user-owned knowledge-base operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    content_type: str
    file_size: int
    status: str
    chunk_count: int
    metadata: dict[str, Any] | None = Field(validation_alias="payload_metadata")
    created_at: datetime
    updated_at: datetime


class DocumentChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    chunk_index: int
    content: str
    page_number: int | None
    metadata: dict[str, Any] | None = Field(validation_alias="payload_metadata")
    created_at: datetime


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    document_ids: list[str] | None = Field(default=None, max_length=50)
    top_k: int | None = Field(default=None, ge=1, le=20)


class KnowledgeSource(BaseModel):
    document_id: str
    filename: str
    chunk_id: str
    chunk_index: int
    page_number: int | None = None
    score: float


class KnowledgeSearchResult(BaseModel):
    content: str
    source: KnowledgeSource


class KnowledgeSearchResponse(BaseModel):
    results: list[KnowledgeSearchResult]
