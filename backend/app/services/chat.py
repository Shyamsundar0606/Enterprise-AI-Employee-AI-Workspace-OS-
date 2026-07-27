from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.repositories.chat import ConversationRepository, MessageRepository

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversation_repository = ConversationRepository(session)
        self.message_repository = MessageRepository(session)

    async def create_conversation(self, *, user_id: int, title: str) -> Conversation:
        conversation = await self.conversation_repository.create(user_id=user_id, title=title)
        logger.info("Conversation created", extra={"user_id": user_id, "conversation_id": conversation.id})
        return conversation

    async def list_conversations(self, *, user_id: int, page: int, page_size: int) -> tuple[list[Conversation], int]:
        return await self.conversation_repository.list_for_user(user_id=user_id, page=page, page_size=page_size)

    async def get_conversation(self, *, conversation_id: str, user_id: int) -> Conversation:
        conversation = await self.conversation_repository.get_by_id(conversation_id=conversation_id, user_id=user_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return conversation

    async def update_conversation(self, *, conversation_id: str, user_id: int, fields: dict[str, Any]) -> Conversation:
        conversation = await self.get_conversation(conversation_id=conversation_id, user_id=user_id)
        updated = await self.conversation_repository.update(conversation, **fields)
        if "title" in fields or "is_archived" in fields:
            logger.info(
                "Conversation updated",
                extra={"user_id": user_id, "conversation_id": conversation_id, "fields": list(fields.keys())},
            )
        return updated

    async def delete_conversation(self, *, conversation_id: str, user_id: int) -> bool:
        conversation = await self.get_conversation(conversation_id=conversation_id, user_id=user_id)
        await self.conversation_repository.delete(conversation)
        logger.info("Conversation deleted", extra={"user_id": user_id, "conversation_id": conversation_id})
        return True

    async def create_message(self, *, conversation_id: str, user_id: int, role: str, content: str, metadata: dict | None, token_count: int | None) -> Message:
        conversation = await self.get_conversation(conversation_id=conversation_id, user_id=user_id)
        message = await self.message_repository.create(
            conversation_id=conversation.id,
            role=role,
            content=content,
            metadata=metadata,
            token_count=token_count,
        )
        conversation.updated_at = conversation.updated_at
        logger.info(
            "Message created",
            extra={"user_id": user_id, "conversation_id": conversation_id, "role": role},
        )
        return message

    async def list_messages(self, *, conversation_id: str, user_id: int, page: int, page_size: int) -> tuple[list[Message], int]:
        await self.get_conversation(conversation_id=conversation_id, user_id=user_id)
        return await self.message_repository.list_for_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            page=page,
            page_size=page_size,
        )
