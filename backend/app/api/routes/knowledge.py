"""Authenticated document and retrieval endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db_session
from app.models.user import User
from app.schemas.chat import DeleteResponse
from app.schemas.knowledge import (
    DocumentChunkOut,
    DocumentOut,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.services.knowledge import KnowledgeError, KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _not_found_or_bad_request(exc: KnowledgeError) -> HTTPException:
    status_code = (
        status.HTTP_404_NOT_FOUND
        if str(exc) == "Document not found"
        else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=status_code, detail=str(exc))


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentOut:
    try:
        content = await file.read()
        document = await KnowledgeService(session).ingest(
            user_id=current_user.id,
            filename=file.filename or "",
            content_type=file.content_type,
            content=content,
        )
        return DocumentOut.model_validate(document)
    except KnowledgeError as exc:
        raise _not_found_or_bad_request(exc) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document storage is temporarily unavailable",
        ) from exc
    finally:
        await file.close()


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[DocumentOut]:
    documents = await KnowledgeService(session).list_documents(user_id=current_user.id)
    return [DocumentOut.model_validate(document) for document in documents]


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentOut:
    try:
        document = await KnowledgeService(session).get_document(
            user_id=current_user.id, document_id=document_id
        )
        return DocumentOut.model_validate(document)
    except KnowledgeError as exc:
        raise _not_found_or_bad_request(exc) from exc


@router.get("/documents/{document_id}/chunks", response_model=list[DocumentChunkOut])
async def list_document_chunks(
    document_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[DocumentChunkOut]:
    try:
        chunks = await KnowledgeService(session).list_chunks(
            user_id=current_user.id, document_id=document_id
        )
        return [DocumentChunkOut.model_validate(chunk) for chunk in chunks]
    except KnowledgeError as exc:
        raise _not_found_or_bad_request(exc) from exc


@router.delete("/documents/{document_id}", response_model=DeleteResponse)
async def delete_document(
    document_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DeleteResponse:
    try:
        await KnowledgeService(session).delete_document(
            user_id=current_user.id, document_id=document_id
        )
        return DeleteResponse(deleted=True, id=document_id)
    except KnowledgeError as exc:
        raise _not_found_or_bad_request(exc) from exc


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    payload: KnowledgeSearchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeSearchResponse:
    try:
        results = await KnowledgeService(session).search(
            user_id=current_user.id,
            query=payload.query,
            document_ids=payload.document_ids,
            top_k=payload.top_k,
        )
        return KnowledgeSearchResponse(results=results)
    except KnowledgeError as exc:
        raise _not_found_or_bad_request(exc) from exc
