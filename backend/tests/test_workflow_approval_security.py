"""Owner isolation and approval decision security tests."""

import importlib
import os
from collections.abc import Iterator

import pytest
from app.integrations.executor import ConnectorExecutor
from app.integrations.schemas import ApprovedActionContext, ConnectorContext
from app.models.workflow import ApprovalStatus
from app.workflows.approvals import ApprovalService
from app.workflows.executor import WorkflowExecutor
from app.workflows.service import WorkflowService
from app.workflows.state_machine import InvalidWorkflowTransition
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: pytest.TempPathFactory) -> Iterator[TestClient]:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'security.db'}"
    os.environ["JWT_SECRET_KEY"] = "approval-security-test-key-with-32-bytes"
    import app.config.settings as settings_module
    import app.database.session as session_module
    import app.main as main_module

    settings_module.get_settings.cache_clear()
    importlib.reload(session_module)
    importlib.reload(main_module)
    with TestClient(main_module.app) as test_client:
        yield test_client


def auth(client: TestClient, username: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"{username}@example.com", "username": username, "password": "secret123"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_pending(client: TestClient, owner: dict[str, str]) -> tuple[str, str]:
    response = client.post(
        "/api/v1/workflows",
        headers=owner,
        json={
            "name": "Protected draft",
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
    workflow_id = response.json()["id"]
    client.post(f"/api/v1/workflows/{workflow_id}/run", headers=owner)
    return workflow_id, client.get("/api/v1/approvals", headers=owner).json()[0]["id"]


def test_cross_user_cannot_read_or_decide_approval(client: TestClient) -> None:
    owner, other = auth(client, "owner"), auth(client, "other")
    _, approval_id = create_pending(client, owner)
    assert client.get("/api/v1/approvals", headers=other).json() == []
    assert client.get(f"/api/v1/approvals/{approval_id}", headers=other).status_code == 404
    assert client.post(f"/api/v1/approvals/{approval_id}/approve", headers=other).status_code == 404
    assert client.post(f"/api/v1/approvals/{approval_id}/reject", headers=other).status_code == 404


def test_client_flags_and_hash_cannot_bypass_approval(client: TestClient) -> None:
    owner = auth(client, "flags")
    workflow_id, approval_id = create_pending(client, owner)
    blocked = client.post(
        f"/api/v1/workflows/{workflow_id}/resume",
        headers=owner,
        json={"approved": True, "action_hash": "f" * 64},
    )
    assert blocked.status_code == 409
    approved = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers=owner,
        json={"approved": True, "action_hash": "0" * 64},
    )
    assert approved.status_code == 200


def test_rejected_approval_cannot_later_execute(client: TestClient) -> None:
    owner = auth(client, "reject")
    _, approval_id = create_pending(client, owner)
    assert client.post(f"/api/v1/approvals/{approval_id}/reject", headers=owner).status_code == 200
    assert client.post(f"/api/v1/approvals/{approval_id}/approve", headers=owner).status_code == 409


@pytest.mark.asyncio
async def test_expiry_mutation_and_forged_contexts_are_rejected(test_user) -> None:
    """Exercise persisted approval validation without bypassing any trusted layer."""
    from datetime import UTC, datetime, timedelta

    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        service = WorkflowService(session)
        workflow = await service.create(
            user_id=test_user.id,
            name="Protected action",
            steps=[
                {
                    "name": "Draft",
                    "step_type": "connector",
                    "connector_id": "local_email",
                    "operation": "create_draft",
                    "arguments": {"to": "manager@example.com", "subject": "A", "body": "B"},
                }
            ],
        )
        await WorkflowExecutor(session).run(
            workflow_id=workflow.id, user_id=test_user.id, role="user"
        )
        approval = (await ApprovalService(session).list_pending(test_user.id))[0]
        approval.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        with pytest.raises(InvalidWorkflowTransition):
            await ApprovalService(session).approve(approval.id, test_user.id)
        assert approval.status == ApprovalStatus.EXPIRED.value

        # A fresh approval whose stored action is subsequently changed is cancelled, not executed.
        workflow = await service.create(
            user_id=test_user.id,
            name="Mutated action",
            steps=[
                {
                    "name": "Draft",
                    "step_type": "connector",
                    "connector_id": "local_email",
                    "operation": "create_draft",
                    "arguments": {"to": "manager@example.com", "subject": "A", "body": "B"},
                }
            ],
        )
        await WorkflowExecutor(session).run(
            workflow_id=workflow.id, user_id=test_user.id, role="user"
        )
        approval = (await ApprovalService(session).list_pending(test_user.id))[0]
        step = (await service.steps(workflow_id=workflow.id, user_id=test_user.id))[0]
        step.arguments = {"to": "manager@example.com", "subject": "Changed", "body": "B"}
        await session.commit()
        with pytest.raises(InvalidWorkflowTransition):
            await ApprovalService(session).approve(approval.id, test_user.id)
        assert approval.status == ApprovalStatus.CANCELLED.value

        # A fabricated context cannot turn an unapproved persisted request into authority.
        forged = ApprovedActionContext(
            approval_id=approval.id,
            workflow_id=workflow.id,
            workflow_step_id=step.id,
            authenticated_user_id=test_user.id + 1,
            action_hash="0" * 64,
        )
        result = await ConnectorExecutor(session=session).execute(
            connector_id="local_email",
            operation="create_draft",
            raw_arguments=step.arguments,
            context=ConnectorContext(authenticated_user_id=test_user.id, role="user"),
            approved_action=forged,
        )
        assert result.status == "approval_required"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    ["authenticated_user_id", "workflow_id", "workflow_step_id", "approval_id", "action_hash"],
)
async def test_each_forged_approval_context_field_is_rejected(test_user, field: str) -> None:
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        service = WorkflowService(session)
        workflow = await service.create(
            user_id=test_user.id,
            name="Forged context",
            steps=[
                {
                    "name": "Draft",
                    "step_type": "connector",
                    "connector_id": "local_email",
                    "operation": "create_draft",
                    "arguments": {"to": "a@example.com", "subject": "A", "body": "B"},
                }
            ],
        )
        await WorkflowExecutor(session).run(
            workflow_id=workflow.id, user_id=test_user.id, role="user"
        )
        approval = (await ApprovalService(session).list_pending(test_user.id))[0]
        await ApprovalService(session).approve(approval.id, test_user.id)
        values = {
            "approval_id": approval.id,
            "workflow_id": workflow.id,
            "workflow_step_id": approval.workflow_step_id,
            "authenticated_user_id": test_user.id,
            "action_hash": approval.action_hash,
        }
        values[field] = (
            test_user.id + 99
            if field == "authenticated_user_id"
            else "f" * 64 if field == "action_hash" else "forged"
        )
        result = await ConnectorExecutor(session=session).execute(
            connector_id="local_email",
            operation="create_draft",
            raw_arguments=approval.sanitized_arguments,
            context=ConnectorContext(authenticated_user_id=test_user.id, role="user"),
            approved_action=ApprovedActionContext(**values),
        )
    assert result.status == "approval_required"


@pytest.mark.asyncio
async def test_approval_for_action_a_cannot_authorize_action_b(test_user) -> None:
    """The stored snapshot binds an approval to its exact connector operation."""
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        service = WorkflowService(session)
        workflow = await service.create(
            user_id=test_user.id,
            name="Action substitution",
            steps=[
                {
                    "name": "Draft",
                    "step_type": "connector",
                    "connector_id": "local_email",
                    "operation": "create_draft",
                    "arguments": {"to": "a@example.com", "subject": "A", "body": "B"},
                }
            ],
        )
        await WorkflowExecutor(session).run(
            workflow_id=workflow.id, user_id=test_user.id, role="user"
        )
        approval = (await ApprovalService(session).list_pending(test_user.id))[0]
        await ApprovalService(session).approve(approval.id, test_user.id)

        result = await ConnectorExecutor(session=session).execute(
            connector_id="local_email",
            operation="send_email",
            raw_arguments=approval.sanitized_arguments,
            context=ConnectorContext(authenticated_user_id=test_user.id, role="user"),
            approved_action=ApprovalService.trusted_context(approval),
        )

    assert result.status == "approval_required"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [("connector_id", "local_calendar"), ("operation", "send_email")],
)
async def test_mutated_stored_connector_action_invalidates_approval(
    test_user, field: str, value: str
) -> None:
    """Changing a persisted connector or operation invalidates its approval hash."""
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        service = WorkflowService(session)
        workflow = await service.create(
            user_id=test_user.id,
            name="Connector mutation",
            steps=[
                {
                    "name": "Draft",
                    "step_type": "connector",
                    "connector_id": "local_email",
                    "operation": "create_draft",
                    "arguments": {"to": "a@example.com", "subject": "A", "body": "B"},
                }
            ],
        )
        await WorkflowExecutor(session).run(
            workflow_id=workflow.id, user_id=test_user.id, role="user"
        )
        approval = (await ApprovalService(session).list_pending(test_user.id))[0]
        step = (await service.steps(workflow_id=workflow.id, user_id=test_user.id))[0]
        setattr(step, field, value)
        await session.commit()

        with pytest.raises(InvalidWorkflowTransition, match="action has changed"):
            await ApprovalService(session).approve(approval.id, test_user.id)

    assert approval.status == ApprovalStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_cancellation_blocks_approved_action_before_execution(test_user) -> None:
    """A separately approved but unconsumed action loses authority on cancellation."""
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        service = WorkflowService(session)
        workflow = await service.create(
            user_id=test_user.id,
            name="Cancel approved action",
            steps=[
                {
                    "name": "Draft",
                    "step_type": "connector",
                    "connector_id": "local_email",
                    "operation": "create_draft",
                    "arguments": {"to": "a@example.com", "subject": "A", "body": "B"},
                }
            ],
        )
        executor = WorkflowExecutor(session)
        await executor.run(workflow_id=workflow.id, user_id=test_user.id, role="user")
        approval = (await ApprovalService(session).list_pending(test_user.id))[0]
        await ApprovalService(session).approve(approval.id, test_user.id)
        approved_context = ApprovalService.trusted_context(approval)
        await service.cancel(workflow_id=workflow.id, user_id=test_user.id)

        after_cancel = await executor.execute_approved(
            workflow_id=workflow.id,
            step_id=approval.workflow_step_id,
            user_id=test_user.id,
            role="user",
            approved=approved_context,
        )
        step = (await service.steps(workflow_id=workflow.id, user_id=test_user.id))[0]

    assert after_cancel is not None
    assert after_cancel.status == "cancelled"
    assert step.status == "cancelled"
    assert step.result is None


@pytest.mark.asyncio
async def test_approved_execution_is_idempotent_after_session_reload(test_user) -> None:
    """Persisted completion and idempotency key prevent a second local draft after reload."""
    from app.database.session import AsyncSessionFactory
    from app.integrations.connectors.email import LocalEmailConnector

    LocalEmailConnector._drafts.clear()
    async with AsyncSessionFactory() as session:
        service = WorkflowService(session)
        workflow = await service.create(
            user_id=test_user.id,
            name="Reload idempotency",
            steps=[
                {
                    "name": "Draft",
                    "step_type": "connector",
                    "connector_id": "local_email",
                    "operation": "create_draft",
                    "arguments": {"to": "a@example.com", "subject": "A", "body": "B"},
                }
            ],
        )
        await WorkflowExecutor(session).run(
            workflow_id=workflow.id, user_id=test_user.id, role="user"
        )
        approval = (await ApprovalService(session).list_pending(test_user.id))[0]
        completed = await ApprovalService(session).approve_and_execute(
            approval.id, test_user.id, "user"
        )
        trusted_context = ApprovalService.trusted_context(approval)
        step_id = approval.workflow_step_id
        workflow_id = workflow.id

    first_drafts = dict(LocalEmailConnector._drafts.get(test_user.id, {}))
    assert completed is not None
    assert len(first_drafts) == 1

    async with AsyncSessionFactory() as reloaded_session:
        reloaded_executor = WorkflowExecutor(reloaded_session)
        replay = await reloaded_executor.execute_approved(
            workflow_id=workflow_id,
            step_id=step_id,
            user_id=test_user.id,
            role="user",
            approved=trusted_context,
        )
        reloaded_step = (
            await WorkflowService(reloaded_session).steps(
                workflow_id=workflow_id, user_id=test_user.id
            )
        )[0]

    assert replay is not None
    assert replay.status == "completed"
    assert reloaded_step.status == "completed"
    assert reloaded_step.idempotency_key is not None
    assert LocalEmailConnector._drafts.get(test_user.id, {}) == first_drafts
