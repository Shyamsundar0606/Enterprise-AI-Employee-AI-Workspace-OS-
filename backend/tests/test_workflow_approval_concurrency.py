"""Deterministic state-level exactly-once approval tests."""

import importlib
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: pytest.TempPathFactory) -> Iterator[TestClient]:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'approval-race.db'}"
    os.environ["JWT_SECRET_KEY"] = "approval-race-test-key"
    import app.config.settings as settings_module
    import app.database.session as session_module
    import app.main as main_module

    settings_module.get_settings.cache_clear()
    importlib.reload(session_module)
    importlib.reload(main_module)
    with TestClient(main_module.app) as test_client:
        yield test_client


def headers(client: TestClient, username: str = "approver") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"{username}@example.com", "username": username, "password": "secret123"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def pending_draft(client: TestClient, auth: dict[str, str]) -> tuple[str, str]:
    workflow = client.post(
        "/api/v1/workflows",
        headers=auth,
        json={
            "name": "Draft once",
            "steps": [
                {
                    "name": "Draft",
                    "step_type": "connector",
                    "connector_id": "local_email",
                    "operation": "create_draft",
                    "arguments": {
                        "to": "manager@example.com",
                        "subject": "Phoenix",
                        "body": "Ready",
                    },
                }
            ],
        },
    )
    workflow_id = workflow.json()["id"]
    assert client.post(f"/api/v1/workflows/{workflow_id}/run", headers=auth).status_code == 200
    approval_id = client.get("/api/v1/approvals", headers=auth).json()[0]["id"]
    return workflow_id, approval_id


def test_repeated_approve_executes_local_draft_once(client: TestClient) -> None:
    auth = headers(client)
    workflow_id, approval_id = pending_draft(client, auth)
    first = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=auth)
    second = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=auth)
    assert first.status_code == 200
    assert second.status_code == 409
    steps = client.get(f"/api/v1/workflows/{workflow_id}/steps", headers=auth).json()
    assert steps[0]["status"] == "completed"
    assert steps[0]["result"]["data"]["draft"]["draft_id"].startswith("draft-")
    assert client.post(f"/api/v1/workflows/{workflow_id}/resume", headers=auth).status_code == 409


def test_approved_decision_cannot_be_rejected(client: TestClient) -> None:
    auth = headers(client)
    _, approval_id = pending_draft(client, auth)
    assert client.post(f"/api/v1/approvals/{approval_id}/approve", headers=auth).status_code == 200
    assert client.post(f"/api/v1/approvals/{approval_id}/reject", headers=auth).status_code == 409


def test_rejected_decision_cannot_be_approved(client: TestClient) -> None:
    auth = headers(client)
    _, approval_id = pending_draft(client, auth)
    assert client.post(f"/api/v1/approvals/{approval_id}/reject", headers=auth).status_code == 200
    assert client.post(f"/api/v1/approvals/{approval_id}/approve", headers=auth).status_code == 409
