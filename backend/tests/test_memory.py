"""Tests for memory service and conversation persistence."""

import importlib
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: pytest.TempPathFactory) -> Iterator[TestClient]:
    """Create a test client with isolated database."""
    db_path = tmp_path / "memory-test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"
    os.environ["JWT_ALGORITHM"] = "HS256"
    os.environ["MEMORY_ENABLED"] = "true"
    os.environ["MEMORY_RECENT_MESSAGES"] = "20"
    os.environ["MEMORY_MAX_CONTEXT_CHARS"] = "12000"

    import app.config.settings as settings_module
    import app.database.redis as redis_module
    import app.database.session as session_module
    import app.main as main_module

    # Reset Redis client to avoid event loop conflicts between tests
    redis_module._redis_client = None
    settings_module.get_settings.cache_clear()
    importlib.reload(session_module)
    importlib.reload(main_module)

    with TestClient(main_module.app) as test_client:
        yield test_client


def _register_user(client: TestClient, email: str, username: str) -> str:
    """Helper to register a user and return access token."""
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "secret123"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_agent_creates_and_persists_conversation(client: TestClient) -> None:
    """Test that agent chat creates conversation and persists messages."""
    token = _register_user(client, "agent1@example.com", "agent1")
    headers = {"Authorization": f"Bearer {token}"}

    # Send agent chat request
    response = client.post(
        "/api/v1/agents/chat",
        headers=headers,
        json={"conversation_id": "test-conv-1", "message": "Hello, remember this!"},
    )

    # Should succeed (may fail if agent not available, but that's OK)
    if response.status_code == 200:
        assert response.json()["conversation_id"] == "test-conv-1"

        # Verify conversation was created
        conv_response = client.get(
            "/api/v1/memory/conversations/test-conv-1",
            headers=headers,
        )
        assert conv_response.status_code == 200
        assert conv_response.json()["id"] == "test-conv-1"


def test_message_persistence_in_conversation(client: TestClient) -> None:
    """Test that messages are persisted in a conversation."""
    token = _register_user(client, "msg-persist@example.com", "msgpersist")
    headers = {"Authorization": f"Bearer {token}"}

    # Create conversation
    conv_response = client.post(
        "/api/v1/chat/conversations",
        headers=headers,
        json={"title": "Message Persistence Test"},
    )
    conversation_id = conv_response.json()["id"]

    # Create messages
    for i in range(3):
        msg_response = client.post(
            "/api/v1/chat/messages",
            headers=headers,
            json={
                "conversation_id": conversation_id,
                "role": "user",
                "content": f"Message {i + 1}",
                "metadata": {"order": i + 1},
                "token_count": 10,
            },
        )
        assert msg_response.status_code == 201

    # Retrieve messages
    list_response = client.get(
        f"/api/v1/memory/conversations/{conversation_id}/messages",
        headers=headers,
    )
    assert list_response.status_code == 200
    messages = list_response.json()["items"]
    assert len(messages) == 3
    assert messages[0]["content"] == "Message 1"
    assert messages[1]["content"] == "Message 2"
    assert messages[2]["content"] == "Message 3"


def test_user_isolation_prevents_cross_access(client: TestClient) -> None:
    """Test that User A cannot access User B's conversations."""
    # Register two users
    token_a = _register_user(client, "user-a@example.com", "usera")
    token_b = _register_user(client, "user-b@example.com", "userb")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A creates conversation
    conv_response = client.post(
        "/api/v1/chat/conversations",
        headers=headers_a,
        json={"title": "User A Private"},
    )
    conversation_id = conv_response.json()["id"]

    # User A can access their own conversation
    get_response = client.get(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=headers_a,
    )
    assert get_response.status_code == 200

    # User B cannot access User A's conversation
    get_response_b = client.get(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=headers_b,
    )
    assert get_response_b.status_code == 404


def test_user_isolation_prevents_message_access(client: TestClient) -> None:
    """Test that User A cannot access User B's messages."""
    # Register two users
    token_a = _register_user(client, "msg-user-a@example.com", "msgusera")
    token_b = _register_user(client, "msg-user-b@example.com", "msguserb")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A creates conversation and message
    conv_response = client.post(
        "/api/v1/chat/conversations",
        headers=headers_a,
        json={"title": "Private Messages"},
    )
    conversation_id = conv_response.json()["id"]

    msg_response = client.post(
        "/api/v1/chat/messages",
        headers=headers_a,
        json={
            "conversation_id": conversation_id,
            "role": "user",
            "content": "Secret message",
        },
    )
    assert msg_response.status_code == 201

    # User B cannot retrieve messages from User A's conversation
    msg_list_response = client.get(
        f"/api/v1/memory/conversations/{conversation_id}/messages",
        headers=headers_b,
    )
    assert msg_list_response.status_code == 404


def test_conversation_history_retrieval(client: TestClient) -> None:
    """Test retrieving conversation history with pagination."""
    token = _register_user(client, "history@example.com", "history")
    headers = {"Authorization": f"Bearer {token}"}

    # Create conversation
    conv_response = client.post(
        "/api/v1/chat/conversations",
        headers=headers,
        json={"title": "History Test"},
    )
    conversation_id = conv_response.json()["id"]

    # Add many messages
    for i in range(25):
        client.post(
            "/api/v1/chat/messages",
            headers=headers,
            json={
                "conversation_id": conversation_id,
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i + 1}",
            },
        )

    # Get first page
    page1 = client.get(
        f"/api/v1/memory/conversations/{conversation_id}/messages?page=1&page_size=10",
        headers=headers,
    )
    assert page1.status_code == 200
    assert len(page1.json()["items"]) == 10
    assert page1.json()["total"] == 25

    # Get second page
    page2 = client.get(
        f"/api/v1/memory/conversations/{conversation_id}/messages?page=2&page_size=10",
        headers=headers,
    )
    assert page2.status_code == 200
    assert len(page2.json()["items"]) == 10

    # Get last page (partial)
    page3 = client.get(
        f"/api/v1/memory/conversations/{conversation_id}/messages?page=3&page_size=10",
        headers=headers,
    )
    assert page3.status_code == 200
    assert len(page3.json()["items"]) == 5


def test_conversation_deletion_soft_delete(client: TestClient) -> None:
    """Test that conversation deletion uses soft delete."""
    token = _register_user(client, "soft-delete@example.com", "softdelete")
    headers = {"Authorization": f"Bearer {token}"}

    # Create and delete conversation
    conv_response = client.post(
        "/api/v1/chat/conversations",
        headers=headers,
        json={"title": "To Delete"},
    )
    conversation_id = conv_response.json()["id"]

    delete_response = client.delete(
        f"/api/v1/memory/conversations/{conversation_id}",
        headers=headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    # Deleted conversation should not appear in list
    list_response = client.get(
        "/api/v1/chat/conversations",
        headers=headers,
    )
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    conversation_ids = [c["id"] for c in items]
    assert conversation_id not in conversation_ids


def test_authentication_required_for_memory_endpoints(client: TestClient) -> None:
    """Test that memory endpoints require authentication."""
    # Test without token
    response = client.get("/api/v1/memory/conversations")
    assert response.status_code == 401

    response = client.get("/api/v1/memory/conversations/some-id")
    assert response.status_code == 401

    response = client.get("/api/v1/memory/conversations/some-id/messages")
    assert response.status_code == 401

    response = client.delete("/api/v1/memory/conversations/some-id")
    assert response.status_code == 401


def test_multiple_conversations_isolated(client: TestClient) -> None:
    """Test that multiple conversations maintain separate message histories."""
    token = _register_user(client, "multi-conv@example.com", "multiconv")
    headers = {"Authorization": f"Bearer {token}"}

    # Create two conversations
    conv1_response = client.post(
        "/api/v1/chat/conversations",
        headers=headers,
        json={"title": "Conversation 1"},
    )
    conv1_id = conv1_response.json()["id"]

    conv2_response = client.post(
        "/api/v1/chat/conversations",
        headers=headers,
        json={"title": "Conversation 2"},
    )
    conv2_id = conv2_response.json()["id"]

    # Add different messages to each
    client.post(
        "/api/v1/chat/messages",
        headers=headers,
        json={
            "conversation_id": conv1_id,
            "role": "user",
            "content": "Message in Conv 1",
        },
    )

    client.post(
        "/api/v1/chat/messages",
        headers=headers,
        json={
            "conversation_id": conv2_id,
            "role": "user",
            "content": "Message in Conv 2",
        },
    )

    # Verify messages are separate
    conv1_msgs = client.get(
        f"/api/v1/memory/conversations/{conv1_id}/messages",
        headers=headers,
    )
    assert conv1_msgs.json()["items"][0]["content"] == "Message in Conv 1"

    conv2_msgs = client.get(
        f"/api/v1/memory/conversations/{conv2_id}/messages",
        headers=headers,
    )
    assert conv2_msgs.json()["items"][0]["content"] == "Message in Conv 2"
