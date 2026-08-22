"""Focused lifecycle audit coverage for persisted workflows."""

import json

import pytest
from app.integrations.schemas import ConnectorErrorDetail, ConnectorResult
from app.models.workflow import WorkflowAuditEvent
from app.workflows.approvals import ApprovalService
from app.workflows.executor import WorkflowExecutor
from app.workflows.service import WorkflowService
from sqlalchemy import select


def read_step() -> dict:
    return {
        "name": "Project status",
        "step_type": "connector",
        "connector_id": "mcp",
        "operation": "project_status",
        "arguments": {},
    }


def email_draft_step() -> dict:
    return {
        "name": "Create draft",
        "step_type": "connector",
        "connector_id": "local_email",
        "operation": "create_draft",
        "arguments": {"to": "manager@example.com", "subject": "Phoenix", "body": "Ready"},
    }


async def event_types(session, workflow_id: str) -> set[str]:
    return set(
        (
            await session.scalars(
                select(WorkflowAuditEvent.event_type).where(
                    WorkflowAuditEvent.workflow_id == workflow_id
                )
            )
        ).all()
    )


@pytest.mark.asyncio
async def test_workflow_lifecycle_events_are_persisted_and_redacted(
    test_user, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every workflow lifecycle path writes safe, owner-bound audit evidence."""
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        service = WorkflowService(session)
        executor = WorkflowExecutor(session)

        completed = await service.create(user_id=test_user.id, name="Complete", steps=[read_step()])
        await executor.run(workflow_id=completed.id, user_id=test_user.id, role="user")

        resumed = await service.create(user_id=test_user.id, name="Resume", steps=[read_step()])
        await executor.resume_workflow(workflow_id=resumed.id, user_id=test_user.id, role="user")

        approved = await service.create(
            user_id=test_user.id, name="Approve", steps=[email_draft_step()]
        )
        await executor.run(workflow_id=approved.id, user_id=test_user.id, role="user")
        approval = (await ApprovalService(session).list_pending(test_user.id))[0]
        await ApprovalService(session).approve_and_execute(approval.id, test_user.id, "user")

        rejected = await service.create(
            user_id=test_user.id, name="Reject", steps=[email_draft_step()]
        )
        await executor.run(workflow_id=rejected.id, user_id=test_user.id, role="user")
        rejection = (await ApprovalService(session).list_pending(test_user.id))[0]
        await ApprovalService(session).reject(rejection.id, test_user.id)

        cancelled = await service.create(user_id=test_user.id, name="Cancel", steps=[read_step()])
        await service.cancel(workflow_id=cancelled.id, user_id=test_user.id)

        async def failed_connector(_executor, **_kwargs) -> ConnectorResult:
            return ConnectorResult(
                connector_id="mcp",
                operation="project_status",
                status="error",
                error=ConnectorErrorDetail(code="connector_input_invalid", message="invalid"),
            )

        monkeypatch.setattr("app.workflows.executor.ConnectorExecutor.execute", failed_connector)
        failed = await service.create(user_id=test_user.id, name="Fail", steps=[read_step()])
        await executor.run(workflow_id=failed.id, user_id=test_user.id, role="user")

        await service.record_event(
            completed,
            "workflow_started",
            {
                "authorization": "Bearer jwt-value",
                "password": "password-value",
                "access_token": "access-value",
                "refresh_token": "refresh-value",
                "api_key": "key-value",
                "secret": "secret-value",
                "system_prompt": "system prompt value",
                "chain_of_thought": "reasoning value",
                "hidden_reasoning": "hidden value",
                "step_id": "safe-step-id",
            },
        )
        await session.commit()

        lifecycle_events = set()
        for workflow in (completed, resumed, approved, rejected, cancelled, failed):
            lifecycle_events.update(await event_types(session, workflow.id))
        audit_metadata = list(
            (
                await session.scalars(
                    select(WorkflowAuditEvent.safe_metadata).where(
                        WorkflowAuditEvent.workflow_id == completed.id
                    )
                )
            ).all()
        )

    assert {
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
    } <= lifecycle_events
    rendered = json.dumps(audit_metadata).lower()
    for sensitive_value in (
        "jwt-value",
        "password-value",
        "access-value",
        "refresh-value",
        "key-value",
        "secret-value",
        "system prompt value",
        "reasoning value",
        "hidden value",
    ):
        assert sensitive_value not in rendered
    assert "safe-step-id" in rendered
