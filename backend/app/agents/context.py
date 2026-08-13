"""Context builder for preparing bounded agent context from conversation history."""

from __future__ import annotations

from typing import Any

from app.config.settings import get_settings


class ContextBuilder:
    """Builds bounded context for LangGraph agent from conversation history."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def build_agent_messages(
        self, *, history: list[dict[str, Any]], user_message: str
    ) -> list[dict[str, str]]:
        """
        Build a list of messages for the agent state.

        Respects memory configuration for:
        - Maximum number of recent messages
        - Maximum context size in characters

        Format: [{"role": "user"|"assistant", "content": "..."}, ...]
        """
        messages: list[dict[str, str]] = []

        # Add recent history (respecting max message count)
        max_messages = self.settings.memory_recent_messages
        recent_history = history[-max_messages:] if len(history) > max_messages else history

        for msg in recent_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        # Respect maximum context size
        max_chars = self.settings.memory_max_context_chars
        truncated_messages = self._truncate_by_context_size(messages, max_chars)

        return truncated_messages

    def _truncate_by_context_size(
        self, messages: list[dict[str, str]], max_chars: int
    ) -> list[dict[str, str]]:
        """
        Truncate messages to fit within max_chars.

        Keeps most recent messages first, removes oldest if necessary.
        """
        total_chars = sum(len(m["content"]) for m in messages)

        if total_chars <= max_chars:
            return messages

        # Start with current message (last one), work backwards
        if not messages:
            return []

        # Always keep the current user message
        current_message = messages[-1]
        result = [current_message]
        current_chars = len(current_message["content"])

        # Add messages backwards (most recent first)
        for msg in reversed(messages[:-1]):
            msg_chars = len(msg["content"])
            if current_chars + msg_chars <= max_chars:
                result.insert(0, msg)
                current_chars += msg_chars
            else:
                break

        return result

    def get_context_stats(self, *, messages: list[dict[str, str]]) -> dict[str, Any]:
        """Get statistics about the current context."""
        total_chars = sum(len(m["content"]) for m in messages)
        return {
            "message_count": len(messages),
            "total_characters": total_chars,
            "max_messages_configured": self.settings.memory_recent_messages,
            "max_context_chars_configured": self.settings.memory_max_context_chars,
        }
