"""Focused authentication boundary tests for M11 workflow HTTP APIs."""

import importlib
import os
from collections.abc import Iterator

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture()
def authenticated_client(tmp_path: pytest.TempPathFactory) -> Iterator[TestClient]:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'workflow-api.db'}"
    os.environ["JWT_SECRET_KEY"] = "workflow-test-secret-key"
    import app.config.settings as settings_module
    import app.database.session as session_module
    import app.main as main_module

    settings_module.get_settings.cache_clear()
    importlib.reload(session_module)
    importlib.reload(main_module)
    with TestClient(main_module.app) as client:
        yield client


def token(client: TestClient, suffix: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"{suffix}@example.com", "username": suffix, "password": "secret123"},
    )
    return response.json()["access_token"]


def workflow_payload() -> dict:
    return {
        "name": "Mailbox",
        "steps": [
            {
                "name": "List",
                "step_type": "connector",
                "connector_id": "local_email",
                "operation": "list_messages",
            }
        ],
    }


def test_authenticated_workflow_ownership(authenticated_client: TestClient) -> None:
    owner = {"Authorization": f"Bearer {token(authenticated_client, 'workflowowner')}"}
    other = {"Authorization": f"Bearer {token(authenticated_client, 'workflowother')}"}
    created = authenticated_client.post(
        "/api/v1/workflows", json={**workflow_payload(), "user_id": 999}, headers=owner
    )
    assert created.status_code == 201
    workflow_id = created.json()["id"]
    assert (
        authenticated_client.get("/api/v1/workflows", headers=owner).json()[0]["id"] == workflow_id
    )
    assert (
        authenticated_client.get(f"/api/v1/workflows/{workflow_id}", headers=other).status_code
        == 404
    )
    assert (
        authenticated_client.get(
            f"/api/v1/workflows/{workflow_id}/steps", headers=owner
        ).status_code
        == 200
    )


def test_owner_can_run_cancel_and_cannot_resume_cancelled(authenticated_client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {token(authenticated_client, 'workflowrunner')}"}
    workflow_id = authenticated_client.post(
        "/api/v1/workflows", json=workflow_payload(), headers=headers
    ).json()["id"]
    assert (
        authenticated_client.post(
            f"/api/v1/workflows/{workflow_id}/run", headers=headers
        ).status_code
        == 200
    )
    assert (
        authenticated_client.post(
            f"/api/v1/workflows/{workflow_id}/cancel", headers=headers
        ).status_code
        == 409
    )


def test_workflows_list_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/workflows")
    assert response.status_code == 401


def test_workflow_create_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows",
            json={"name": "Unauthorised", "steps": []},
        )
    assert response.status_code == 401


def test_approvals_list_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/approvals")
    assert response.status_code == 401


def test_approval_approve_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/approvals/not-owned/approve")
    assert response.status_code == 401
