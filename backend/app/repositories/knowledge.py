"""Persistence operations for the knowledge base."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_document(
        self,
        *,
        user_id: int,
        original_filename: str,
        stored_filename: str,
        content_type: str,
        file_size: int,
    ) -> Document:
        document = Document(
            user_id=user_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            content_type=content_type,
            file_size=file_size,
            status="pending",
            payload_metadata={"source_filename": original_filename},
        )
        self.session.add(document)
        await self.session.flush()
        await self.session.commit()
        return document

    async def get_document(self, *, document_id: str, user_id: int) -> Document | None:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_documents(self, *, user_id: int) -> list[Document]:
        result = await self.session.execute(
            select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def set_document_status(
        self, document: Document, *, status: str, chunk_count: int | None = None
    ) -> Document:
        document.status = status
        if chunk_count is not None:
            document.chunk_count = chunk_count
        document.updated_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.commit()
        return document

    async def add_chunks(self, chunks: Sequence[DocumentChunk]) -> None:
        self.session.add_all(chunks)
        await self.session.flush()

    async def list_chunks(self, *, document_id: str, user_id: int) -> list[DocumentChunk]:
        result = await self.session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id, DocumentChunk.user_id == user_id)
            .order_by(DocumentChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def list_searchable_chunks(
        self, *, user_id: int, document_ids: set[str] | None = None
    ) -> list[tuple[DocumentChunk, Document]]:
        statement: Select[tuple[DocumentChunk, Document]] = (
            select(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(DocumentChunk.user_id == user_id, Document.user_id == user_id, Document.status == "ready")
        )
        if document_ids:
            statement = statement.where(Document.id.in_(document_ids))
        result = await self.session.execute(statement.order_by(DocumentChunk.chunk_index))
        return list(result.all())

    async def delete_document(self, document: Document) -> None:
        await self.session.delete(document)
        await self.session.commit()
