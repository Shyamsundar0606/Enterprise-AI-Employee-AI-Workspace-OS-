"""Focused persisted workflow cancellation and resume lifecycle tests."""

import pytest
import pytest_asyncio
from app.models.workflow import WorkflowStatus
from app.workflows.executor import WorkflowExecutor
from app.workflows.service import WorkflowService, WorkflowValidationError
from app.workflows.state_machine import InvalidWorkflowTransition


@pytest_asyncio.fixture(autouse=True)
async def dispose_database_engine_between_lifecycle_tests() -> None:
    yield
    from app.database.session import engine

    await engine.dispose()


def read_step() -> dict:
    return {
        "name": "Status",
        "step_type": "connector",
        "connector_id": "mcp",
        "operation": "project_status",
        "arguments": {},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow_status", ["pending", "running"])
async def test_pending_or_running_workflow_can_be_cancelled(test_user, workflow_status) -> None:
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        workflow = await WorkflowService(session).create(
            user_id=test_user.id, name="Cancel", steps=[read_step()]
        )
        workflow.status = workflow_status
        await session.commit()
        cancelled = await WorkflowService(session).cancel(
            workflow_id=workflow.id, user_id=test_user.id
        )
    assert cancelled is not None and cancelled.status == "cancelled"


@pytest.mark.asyncio
async def test_waiting_workflow_cancellation_cancels_pending_approval(test_user) -> None:
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        workflow = await WorkflowService(session).create(
            user_id=test_user.id,
            name="Approval cancel",
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
        await WorkflowService(session).cancel(workflow_id=workflow.id, user_id=test_user.id)
        from app.workflows.approvals import ApprovalService

        assert await ApprovalService(session).list_pending(test_user.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "cancelled", "completed"])
async def test_terminal_workflows_cannot_resume(test_user, status) -> None:
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        workflow = await WorkflowService(session).create(
            user_id=test_user.id, name="Terminal", steps=[read_step()]
        )
        workflow.status = status
        await session.commit()
        with pytest.raises(InvalidWorkflowTransition):
            await WorkflowExecutor(session).resume_workflow(
                workflow_id=workflow.id, user_id=test_user.id, role="user"
            )


@pytest.mark.asyncio
async def test_completed_workflow_cannot_be_cancelled(test_user) -> None:
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        workflow = await WorkflowService(session).create(
            user_id=test_user.id, name="Done", steps=[read_step()]
        )
        workflow.status = WorkflowStatus.COMPLETED.value
        await session.commit()
        with pytest.raises(WorkflowValidationError):
            await WorkflowService(session).cancel(workflow_id=workflow.id, user_id=test_user.id)
