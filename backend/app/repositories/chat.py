from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models.conversation import Conversation
from app.models.message import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, user_id: int, title: str) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        self.session.add(conversation)
        await self.session.flush()
        await self.session.commit()
        return conversation

    async def get_by_id(self, *, conversation_id: str, user_id: int) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, *, user_id: int, page: int, page_size: int
    ) -> tuple[list[Conversation], int]:
        statement = (
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.is_deleted.is_(False))
            .order_by(Conversation.updated_at.desc())
        )
        count_query = (
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == user_id, Conversation.is_deleted.is_(False))
        )
        result = await self.session.execute(
            statement.offset((page - 1) * page_size).limit(page_size)
        )
        rows = result.scalars().all()
        total = (await self.session.execute(count_query)).scalar_one()
        return rows, total

    async def update(self, conversation: Conversation, **fields: Any) -> Conversation:
        for key, value in fields.items():
            if value is not None:
                setattr(conversation, key, value)
        conversation.updated_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.commit()
        return conversation

    async def delete(self, conversation: Conversation) -> bool:
        conversation.is_deleted = True
        conversation.deleted_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.commit()
        return True


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict | None,
        token_count: int | None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            payload_metadata=metadata,
            token_count=token_count,
        )
        self.session.add(message)
        await self.session.flush()
        await self.session.commit()
        return message

    async def list_for_conversation(
        self, *, conversation_id: str, user_id: int, page: int, page_size: int
    ) -> tuple[list[Message], int]:
        statement = (
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.is_deleted.is_(False),
            )
            .order_by(Message.created_at.asc())
        )
        result = await self.session.execute(
            statement.offset((page - 1) * page_size).limit(page_size)
        )
        count = await self.session.execute(
            select(func.count())
            .select_from(Message)
            .join(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all()), count.scalar_one()
