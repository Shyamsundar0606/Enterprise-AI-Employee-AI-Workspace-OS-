"""Focused approval API authentication and ownership boundaries."""

import importlib
import os
from collections.abc import Iterator

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture()
def approval_client(tmp_path: pytest.TempPathFactory) -> Iterator[TestClient]:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'approval-api.db'}"
    os.environ["JWT_SECRET_KEY"] = "approval-test-secret-key"
    import app.config.settings as settings_module
    import app.database.session as session_module
    import app.main as main_module

    settings_module.get_settings.cache_clear()
    importlib.reload(session_module)
    importlib.reload(main_module)
    with TestClient(main_module.app) as client:
        yield client


def approval_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "approver@example.com", "username": "approver", "password": "secret123"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_approved_local_email_draft_executes_once(approval_client: TestClient) -> None:
    headers = approval_headers(approval_client)
    created = approval_client.post(
        "/api/v1/workflows",
        headers=headers,
        json={
            "name": "Draft update",
            "steps": [
                {
                    "name": "Create draft",
                    "step_type": "connector",
                    "connector_id": "local_email",
                    "operation": "create_draft",
                    "arguments": {
                        "to": "manager@example.com",
                        "subject": "Project Phoenix Update",
                        "body": "The report is ready.",
                    },
                }
            ],
        },
    )
    assert created.status_code == 201
    workflow_id = created.json()["id"]
    paused = approval_client.post(f"/api/v1/workflows/{workflow_id}/run", headers=headers)
    assert paused.status_code == 200 and paused.json()["status"] == "waiting_for_approval"
    approval = approval_client.get("/api/v1/approvals", headers=headers).json()[0]
    approved = approval_client.post(f"/api/v1/approvals/{approval['id']}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["approval"]["status"] == "approved"
    assert approved.json()["workflow_status"] == "completed"
    steps = approval_client.get(f"/api/v1/workflows/{workflow_id}/steps", headers=headers).json()
    assert steps[0]["status"] == "completed"
    assert steps[0]["result"]["data"]["draft"]["subject"] == "Project Phoenix Update"
    repeated = approval_client.post(f"/api/v1/approvals/{approval['id']}/approve", headers=headers)
    assert repeated.status_code == 409


def test_approvals_list_requires_authentication() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/approvals").status_code == 401


def test_approval_get_requires_authentication() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/approvals/not-owned").status_code == 401


def test_approval_approve_requires_authentication() -> None:
    with TestClient(app) as client:
        assert client.post("/api/v1/approvals/not-owned/approve").status_code == 401


def test_approval_reject_requires_authentication() -> None:
    with TestClient(app) as client:
        assert client.post("/api/v1/approvals/not-owned/reject").status_code == 401
