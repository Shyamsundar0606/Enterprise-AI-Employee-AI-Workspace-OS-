import importlib
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: pytest.TempPathFactory) -> Iterator[TestClient]:
    db_path = tmp_path / "auth-test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"
    os.environ["JWT_ALGORITHM"] = "HS256"

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


def test_register_login_and_profile(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "username": "alice",
            "password": "secret123",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["email"] == "alice@example.com"
    assert payload["access_token"]
    assert payload["refresh_token"]

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "secret123"},
    )

    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["access_token"]
    assert login_payload["refresh_token"]

    profile_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )

    assert profile_response.status_code == 200
    assert profile_response.json()["email"] == "alice@example.com"


def test_refresh_token_rotates_session(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "bob@example.com",
            "username": "bob",
            "password": "secret123",
        },
    )

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "secret123"},
    )

    refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_response.json()["refresh_token"]},
    )

    assert refresh_response.status_code == 200
    assert refresh_response.json()["access_token"]
    assert refresh_response.json()["refresh_token"]


def test_admin_route_requires_admin(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "carol@example.com",
            "username": "carol",
            "password": "secret123",
            "role": "user",
        },
    )

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "secret123"},
    )

    response = client.get(
        "/api/v1/auth/admin",
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )

    assert response.status_code == 403
