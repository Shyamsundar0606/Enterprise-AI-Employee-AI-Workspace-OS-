"""Tests for context building and memory management utilities."""

import pytest
from app.agents.context import ContextBuilder


@pytest.fixture()
def context_builder() -> ContextBuilder:
    """Create a context builder for testing."""
    return ContextBuilder()


def test_context_builder_respects_message_limit(context_builder: ContextBuilder) -> None:
    """Test that context builder respects max message limit."""
    # Create 30 messages
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
        for i in range(30)
    ]

    # Build with default limit (20)
    messages = context_builder.build_agent_messages(history=history, user_message="New message")

    # Should have at most 20 + 1 (new message)
    assert len(messages) <= 21
    # Should include the new message
    assert messages[-1]["content"] == "New message"


def test_context_builder_respects_context_size_limit(context_builder: ContextBuilder) -> None:
    """Test that context builder respects max context character limit."""
    # Create history with very large messages
    history = [
        {"role": "user", "content": "x" * 5000},
        {"role": "assistant", "content": "y" * 5000},
        {"role": "user", "content": "z" * 5000},
    ]

    messages = context_builder.build_agent_messages(history=history, user_message="New message")

    total_chars = sum(len(m["content"]) for m in messages)
    assert total_chars <= 12000  # Default max context chars


def test_context_builder_includes_current_message(context_builder: ContextBuilder) -> None:
    """Test that context builder always includes current user message."""
    history = []

    messages = context_builder.build_agent_messages(
        history=history, user_message="Current question"
    )

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Current question"


def test_context_builder_preserves_message_order(context_builder: ContextBuilder) -> None:
    """Test that context builder preserves message order."""
    history = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "Response 1"},
        {"role": "user", "content": "Second"},
        {"role": "assistant", "content": "Response 2"},
    ]

    messages = context_builder.build_agent_messages(history=history, user_message="Third")

    # Should preserve order
    assert messages[0]["content"] == "First"
    assert messages[1]["content"] == "Response 1"
    assert messages[2]["content"] == "Second"
    assert messages[3]["content"] == "Response 2"
    assert messages[4]["content"] == "Third"


def test_context_builder_empty_history(context_builder: ContextBuilder) -> None:
    """Test context builder with empty history."""
    messages = context_builder.build_agent_messages(history=[], user_message="Hello")

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"


def test_context_builder_stats(context_builder: ContextBuilder) -> None:
    """Test getting context statistics."""
    messages = [
        {"role": "user", "content": "Hello world"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    stats = context_builder.get_context_stats(messages=messages)

    assert stats["message_count"] == 2
    assert stats["total_characters"] == len("Hello world") + len("Hi there!")
    assert stats["max_messages_configured"] == 20
    assert stats["max_context_chars_configured"] == 12000


def test_context_builder_truncate_by_size(context_builder: ContextBuilder) -> None:
    """Test message truncation by context size."""
    messages = [
        {"role": "user", "content": "x" * 1000},
        {"role": "assistant", "content": "y" * 1000},
        {"role": "user", "content": "z" * 1000},
        {"role": "assistant", "content": "Last message"},
    ]

    truncated = context_builder._truncate_by_context_size(messages, max_chars=2500)

    # Should keep at least the last message
    assert truncated[-1]["content"] == "Last message"
    # Should respect size limit
    total_chars = sum(len(m["content"]) for m in truncated)
    assert total_chars <= 2500
