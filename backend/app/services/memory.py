"""Memory service for managing conversation history and context."""

from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.database.redis import get_redis_client
from app.models.conversation import Conversation
from app.models.message import Message
from app.repositories.chat import ConversationRepository, MessageRepository

logger = logging.getLogger(__name__)


class MemoryService:
    """Manages conversation memory and persistent context."""

    def __init__(self, session: AsyncSession, redis_client: Redis | None = None) -> None:
        self.session = session
        self.redis_client = redis_client or get_redis_client()
        self.conversation_repository = ConversationRepository(session)
        self.message_repository = MessageRepository(session)
        self.settings = get_settings()

    async def verify_conversation_owner(self, *, conversation_id: str, user_id: int) -> bool:
        """Verify that the user owns the conversation."""
        conversation = await self.conversation_repository.get_by_id(
            conversation_id=conversation_id, user_id=user_id
        )
        return conversation is not None

    async def get_conversation(self, *, conversation_id: str, user_id: int) -> Conversation | None:
        """Get a conversation if it exists and user owns it."""
        return await self.conversation_repository.get_by_id(
            conversation_id=conversation_id, user_id=user_id
        )

    async def get_or_create_conversation(
        self, *, conversation_id: str, user_id: int, title: str | None = None
    ) -> Conversation:
        """Get existing conversation or create a new one."""
        conversation = await self.get_conversation(conversation_id=conversation_id, user_id=user_id)
        if conversation is None:
            # Create new conversation with provided conversation_id
            conversation = Conversation(
                id=conversation_id, user_id=user_id, title=title or conversation_id
            )
            self.session.add(conversation)
            await self.session.flush()
            await self.session.commit()
            logger.info(
                "Conversation created",
                extra={"user_id": user_id, "conversation_id": conversation_id},
            )
        return conversation

    async def save_message(
        self,
        *,
        conversation_id: str,
        user_id: int,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        token_count: int | None = None,
    ) -> Message:
        """Save a message to a conversation."""
        # Verify conversation exists and user owns it
        conversation = await self.get_conversation(conversation_id=conversation_id, user_id=user_id)
        if conversation is None:
            raise ValueError(
                f"Conversation {conversation_id} not found or user {user_id} does not own it"
            )

        message = await self.message_repository.create(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata,
            token_count=token_count,
        )

        # Invalidate Redis cache for this conversation
        await self._invalidate_conversation_cache(conversation_id)

        logger.info(
            "Message saved",
            extra={"user_id": user_id, "conversation_id": conversation_id, "role": role},
        )
        return message

    async def get_recent_messages(
        self, *, conversation_id: str, user_id: int, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """
        Get recent messages for a conversation.

        Attempts Redis cache first, falls back to database.
        """
        if limit is None:
            limit = self.settings.memory_recent_messages

        # Try Redis cache
        cache_key = f"conversation:{conversation_id}:messages"
        try:
            cached = await self.redis_client.get(cache_key)
            if cached:
                messages = json.loads(cached)
                logger.debug(
                    "Cache hit for conversation messages",
                    extra={"conversation_id": conversation_id},
                )
                return messages[-limit:] if len(messages) > limit else messages
        except Exception as e:
            logger.warning(
                "Redis cache error, falling back to database",
                extra={"error": str(e), "conversation_id": conversation_id},
            )

        # Fallback to database
        messages, _ = await self.message_repository.list_for_conversation(
            conversation_id=conversation_id, user_id=user_id, page=1, page_size=limit
        )

        # Format for response
        formatted = [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "metadata": m.payload_metadata,
                "token_count": m.token_count,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]

        # Cache in Redis
        try:
            await self.redis_client.setex(
                cache_key,
                self.settings.memory_redis_ttl_seconds,
                json.dumps(formatted),
            )
        except Exception as e:
            logger.warning(
                "Failed to cache messages in Redis",
                extra={"error": str(e), "conversation_id": conversation_id},
            )

        return formatted

    async def get_conversation_history(
        self, *, conversation_id: str, user_id: int, page: int = 1, page_size: int = 100
    ) -> tuple[list[dict[str, Any]], int]:
        """Get full conversation history with pagination."""
        messages, total = await self.message_repository.list_for_conversation(
            conversation_id=conversation_id, user_id=user_id, page=page, page_size=page_size
        )

        formatted = [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "metadata": m.payload_metadata,
                "token_count": m.token_count,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]

        return formatted, total

    async def clear_conversation_cache(self, *, conversation_id: str) -> None:
        """Clear Redis cache for a conversation."""
        await self._invalidate_conversation_cache(conversation_id)

    async def _invalidate_conversation_cache(self, conversation_id: str) -> None:
        """Internal method to invalidate conversation cache."""
        cache_key = f"conversation:{conversation_id}:messages"
        try:
            await self.redis_client.delete(cache_key)
        except Exception as e:
            logger.warning(
                "Failed to invalidate Redis cache",
                extra={"error": str(e), "conversation_id": conversation_id},
            )
