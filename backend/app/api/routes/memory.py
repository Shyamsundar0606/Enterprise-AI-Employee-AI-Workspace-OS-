"""Memory management endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db_session
from app.models.user import User
from app.schemas.chat import (
    ConversationOut,
    DeleteResponse,
    MessageListResponse,
    MessageOut,
)
from app.services.memory import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])
logger = logging.getLogger(__name__)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_user_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> list[ConversationOut]:
    """List all conversations for the authenticated user."""
    memory_service = MemoryService(session)
    conversations, _ = await memory_service.conversation_repository.list_for_user(
        user_id=current_user.id, page=1, page_size=1000
    )
    return [ConversationOut.model_validate(c) for c in conversations]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> ConversationOut:
    """Get a specific conversation with user ownership verification."""
    memory_service = MemoryService(session)
    conversation = await memory_service.get_conversation(
        conversation_id=conversation_id, user_id=current_user.id
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return ConversationOut.model_validate(conversation)


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    conversation_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
) -> MessageListResponse:
    """Get all messages in a conversation."""
    memory_service = MemoryService(session)

    # Verify conversation exists and user owns it
    if not await memory_service.verify_conversation_owner(
        conversation_id=conversation_id, user_id=current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    messages, total = await memory_service.get_conversation_history(
        conversation_id=conversation_id, user_id=current_user.id, page=page, page_size=page_size
    )

    return MessageListResponse(
        items=[
            MessageOut(
                id=m["id"],
                conversation_id=conversation_id,
                role=m["role"],
                content=m["content"],
                metadata=m["metadata"],
                token_count=m["token_count"],
                created_at=m["created_at"],
            )
            for m in messages
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/conversations/{conversation_id}", response_model=DeleteResponse)
async def delete_conversation(
    conversation_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> DeleteResponse:
    """Delete a conversation (soft delete)."""
    memory_service = MemoryService(session)
    conversation = await memory_service.get_conversation(
        conversation_id=conversation_id, user_id=current_user.id
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    deleted = await memory_service.conversation_repository.delete(conversation)
    logger.info(
        "Conversation deleted",
        extra={"user_id": current_user.id, "conversation_id": conversation_id},
    )
    return DeleteResponse(deleted=deleted, id=conversation_id)
