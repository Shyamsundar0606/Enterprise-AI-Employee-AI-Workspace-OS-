import importlib
import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: pytest.TempPathFactory) -> Iterator[TestClient]:
    db_path = tmp_path / "chat-test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"
    os.environ["JWT_ALGORITHM"] = "HS256"

    import app.config.settings as settings_module
    import app.database.session as session_module
    import app.main as main_module

    settings_module.get_settings.cache_clear()
    importlib.reload(session_module)
    importlib.reload(main_module)

    with TestClient(main_module.app) as test_client:
        yield test_client


def _register_user(client: TestClient, email: str, username: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "secret123"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_conversation_crud(client: TestClient) -> None:
    token = _register_user(client, "chat@example.com", "chat")
    headers = {"Authorization": f"Bearer {token}"}

    create_response = client.post(
        "/api/v1/chat/conversations",
        headers=headers,
        json={"title": "Project sync"},
    )
    assert create_response.status_code == 201
    conversation = create_response.json()
    assert conversation["title"] == "Project sync"
    assert conversation["is_archived"] is False

    list_response = client.get("/api/v1/chat/conversations", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1

    detail_response = client.get(
        f"/api/v1/chat/conversations/{conversation['id']}",
        headers=headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == conversation["id"]

    patch_response = client.patch(
        f"/api/v1/chat/conversations/{conversation['id']}",
        headers=headers,
        json={"title": "Updated title", "is_archived": True},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["title"] == "Updated title"
    assert patch_response.json()["is_archived"] is True

    delete_response = client.delete(
        f"/api/v1/chat/conversations/{conversation['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True


def test_message_crud(client: TestClient) -> None:
    token = _register_user(client, "msg@example.com", "msg")
    headers = {"Authorization": f"Bearer {token}"}

    conversation_response = client.post(
        "/api/v1/chat/conversations",
        headers=headers,
        json={"title": "Messages"},
    )
    conversation_id = conversation_response.json()["id"]

    create_message_response = client.post(
        "/api/v1/chat/messages",
        headers=headers,
        json={
            "conversation_id": conversation_id,
            "role": "user",
            "content": "Hello world",
            "metadata": {"source": "web"},
            "token_count": 2,
        },
    )
    assert create_message_response.status_code == 201
    message = create_message_response.json()
    assert message["content"] == "Hello world"
    assert message["role"] == "user"

    list_messages_response = client.get(
        f"/api/v1/chat/messages/{conversation_id}",
        headers=headers,
    )
    assert list_messages_response.status_code == 200
    assert len(list_messages_response.json()["items"]) == 1


def test_authentication_required_for_chat_routes(client: TestClient) -> None:
    response = client.get("/api/v1/chat/conversations")
    assert response.status_code == 401


def test_websocket_echo(client: TestClient) -> None:
    token = _register_user(client, "socket@example.com", "socket")
    with client.websocket_connect(
        "/ws/chat",
        headers={"Authorization": f"Bearer {token}"},
    ) as websocket:
        websocket.send_text("hello")
        assert websocket.receive_text() == "hello"
