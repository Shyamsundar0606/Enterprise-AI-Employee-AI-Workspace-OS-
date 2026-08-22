"""Authentication, ownership, and payload-safety checks for workflow SSE."""

import importlib
import json
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: pytest.TempPathFactory) -> Iterator[TestClient]:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'workflow-sse.db'}"
    os.environ["JWT_SECRET_KEY"] = "workflow-sse-test-key-with-at-least-32-bytes"
    import app.config.settings as settings_module
    import app.database.session as session_module
    import app.main as main_module

    settings_module.get_settings.cache_clear()
    importlib.reload(session_module)
    importlib.reload(main_module)
    with TestClient(main_module.app) as test_client:
        yield test_client


def auth_headers(client: TestClient, username: str) -> tuple[dict[str, str], str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"{username}@example.com", "username": username, "password": "secret123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, token


def test_workflow_sse_requires_owner_authentication_and_emits_safe_payloads(
    client: TestClient,
) -> None:
    owner, owner_token = auth_headers(client, "sseowner")
    other, _ = auth_headers(client, "sseother")
    created = client.post(
        "/api/v1/workflows",
        headers=owner,
        json={
            "name": "SSE workflow",
            "steps": [
                {
                    "name": "Status",
                    "step_type": "connector",
                    "connector_id": "mcp",
                    "operation": "project_status",
                }
            ],
        },
    )
    workflow_id = created.json()["id"]
    assert client.post(f"/api/v1/workflows/{workflow_id}/run", headers=owner).status_code == 200
    assert client.get(f"/api/v1/workflows/{workflow_id}/events").status_code == 401
    assert client.get(f"/api/v1/workflows/{workflow_id}/events", headers=other).status_code == 404

    response = client.get(f"/api/v1/workflows/{workflow_id}/events", headers=owner)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    allowed = {
        "workflow_created",
        "workflow_started",
        "step_started",
        "step_completed",
        "step_failed",
        "approval_requested",
        "approval_approved",
        "approval_rejected",
        "approved_action_executed",
        "workflow_resumed",
        "workflow_cancelled",
        "workflow_completed",
        "workflow_failed",
    }
    assert payloads
    assert {item["type"] for item in payloads} <= allowed
    rendered = response.text.lower()
    for forbidden in (
        owner_token.lower(),
        "authorization",
        "password",
        "access_token",
        "refresh_token",
        "api_key",
        "secret",
        "system prompt",
        "chain-of-thought",
        "hidden reasoning",
    ):
        assert forbidden not in rendered
    assert all(set(item["metadata"]) <= {"step_id", "approval_id"} for item in payloads)
