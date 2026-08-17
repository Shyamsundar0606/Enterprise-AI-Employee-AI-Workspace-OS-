"""Document ingestion and user-isolated semantic retrieval."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.models.document import Document, DocumentChunk
from app.repositories.knowledge import KnowledgeRepository
from app.schemas.knowledge import KnowledgeSearchResult, KnowledgeSource
from app.services.chunking import TextChunker
from app.services.document_extraction import DocumentExtractionError, DocumentExtractor
from app.services.embeddings import EmbeddingError, EmbeddingService

logger = logging.getLogger(__name__)


class KnowledgeError(ValueError):
    """A safe client-facing knowledge-base operation failure."""


class DocumentStorage:
    """Writes files using server-generated identifiers only."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_settings().document_storage_path

    async def save(self, *, stored_filename: str, content: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / stored_filename
        path.write_bytes(content)

    async def delete(self, stored_filename: str) -> None:
        path = self.root / stored_filename
        if path.exists():
            path.unlink()


class KnowledgeService:
    """Coordinates safe ingestion and user-filtered retrieval."""

    _ALLOWED_TYPES = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".pdf": "application/pdf",
    }

    def __init__(
        self,
        session: AsyncSession,
        *,
        embedding_service: EmbeddingService | None = None,
        extractor: DocumentExtractor | None = None,
        storage: DocumentStorage | None = None,
    ) -> None:
        self.repository = KnowledgeRepository(session)
        self.session = session
        self.embeddings = embedding_service or EmbeddingService()
        self.extractor = extractor or DocumentExtractor()
        self.storage = storage or DocumentStorage()
        self.settings = get_settings()

    async def ingest(
        self,
        *,
        user_id: int,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> Document:
        suffix, normalized_type = self._validate_upload(
            filename=filename, content_type=content_type, content=content
        )
        stored_filename = f"{uuid4()}{suffix}"
        document = await self.repository.create_document(
            user_id=user_id,
            original_filename=Path(filename).name,
            stored_filename=stored_filename,
            content_type=normalized_type,
            file_size=len(content),
        )
        await self.repository.set_document_status(document, status="processing")
        try:
            pages = await self.extractor.extract(content=content, content_type=normalized_type)
            chunks = TextChunker(
                chunk_size=self.settings.rag_chunk_size,
                overlap=self.settings.rag_chunk_overlap,
            ).chunk(pages)
            if not chunks:
                raise KnowledgeError("Document contains no indexable text")
            vectors = await self.embeddings.embed_batch([chunk.content for chunk in chunks])
            await self.storage.save(stored_filename=stored_filename, content=content)
            await self.repository.add_chunks(
                [
                    DocumentChunk(
                        document_id=document.id,
                        user_id=user_id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        embedding=vector,
                        page_number=chunk.page_number,
                        payload_metadata={"filename": document.original_filename},
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ]
            )
            await self.repository.set_document_status(
                document, status="ready", chunk_count=len(chunks)
            )
        except (DocumentExtractionError, EmbeddingError, KnowledgeError) as exc:
            await self.session.rollback()
            await self.storage.delete(stored_filename)
            document = await self.repository.get_document(document_id=document.id, user_id=user_id)
            if document is not None:
                await self.repository.set_document_status(document, status="failed", chunk_count=0)
            raise KnowledgeError(str(exc)) from exc
        except Exception as exc:
            await self.session.rollback()
            await self.storage.delete(stored_filename)
            document = await self.repository.get_document(document_id=document.id, user_id=user_id)
            if document is not None:
                await self.repository.set_document_status(document, status="failed", chunk_count=0)
            logger.exception("Document ingestion failed", extra={"document_id": document.id})
            raise KnowledgeError("Document could not be processed safely") from exc
        return document

    async def get_document(self, *, user_id: int, document_id: str) -> Document:
        document = await self.repository.get_document(document_id=document_id, user_id=user_id)
        if document is None:
            raise KnowledgeError("Document not found")
        return document

    async def list_documents(self, *, user_id: int) -> list[Document]:
        return await self.repository.list_documents(user_id=user_id)

    async def list_chunks(self, *, user_id: int, document_id: str) -> list[DocumentChunk]:
        await self.get_document(user_id=user_id, document_id=document_id)
        return await self.repository.list_chunks(document_id=document_id, user_id=user_id)

    async def delete_document(self, *, user_id: int, document_id: str) -> None:
        document = await self.get_document(user_id=user_id, document_id=document_id)
        stored_filename = document.stored_filename
        await self.repository.delete_document(document)
        await self.storage.delete(stored_filename)

    async def search(
        self,
        *,
        user_id: int,
        query: str,
        document_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> list[KnowledgeSearchResult]:
        if not query.strip():
            raise KnowledgeError("Search query must not be empty")
        if document_ids:
            owned = await self.repository.list_searchable_chunks(
                user_id=user_id, document_ids=set(document_ids)
            )
        else:
            owned = await self.repository.list_searchable_chunks(user_id=user_id)
        if not owned:
            return []
        query_vector = await self.embeddings.embed(query)
        results: list[KnowledgeSearchResult] = []
        for chunk, document in owned:
            score = self._cosine_similarity(query_vector, chunk.embedding)
            if score < self.settings.rag_similarity_threshold:
                continue
            results.append(
                KnowledgeSearchResult(
                    content=chunk.content,
                    source=KnowledgeSource(
                        document_id=document.id,
                        filename=document.original_filename,
                        chunk_id=chunk.id,
                        chunk_index=chunk.chunk_index,
                        page_number=chunk.page_number,
                        score=round(score, 6),
                    ),
                )
            )
        results.sort(key=lambda result: result.source.score, reverse=True)
        return results[: top_k or self.settings.rag_top_k]

    def _validate_upload(
        self, *, filename: str, content_type: str | None, content: bytes
    ) -> tuple[str, str]:
        safe_filename = Path(filename).name
        if not filename or safe_filename != filename or Path(filename).is_absolute():
            raise KnowledgeError("Filename is invalid")
        suffix = Path(safe_filename).suffix.lower()
        expected_type = self._ALLOWED_TYPES.get(suffix)
        if expected_type is None:
            raise KnowledgeError("Unsupported document type")
        if content_type and content_type.split(";", 1)[0].lower() != expected_type:
            raise KnowledgeError("File content type does not match its extension")
        if not content:
            raise KnowledgeError("Uploaded file is empty")
        if len(content) > self.settings.max_document_size_mb * 1024 * 1024:
            raise KnowledgeError("Uploaded file exceeds the configured size limit")
        return suffix, expected_type

    @staticmethod
    def _cosine_similarity(query: list[float], embedding: list[float]) -> float:
        if len(query) != len(embedding):
            return 0.0
        denominator = math.sqrt(sum(value * value for value in query)) * math.sqrt(
            sum(value * value for value in embedding)
        )
        if denominator == 0:
            return 0.0
        return sum(left * right for left, right in zip(query, embedding, strict=True)) / denominator
