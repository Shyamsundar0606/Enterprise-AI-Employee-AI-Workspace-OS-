"""Focused persisted retry tests for safe workflow steps."""

from __future__ import annotations

import pytest
import pytest_asyncio
from app.integrations.schemas import ConnectorErrorDetail, ConnectorResult
from app.services.knowledge import KnowledgeError, KnowledgeService
from app.tools.schemas import ToolErrorDetail, ToolResult
from app.workflows.executor import WorkflowExecutor, is_retryable_workflow_failure
from app.workflows.service import WorkflowService


@pytest_asyncio.fixture(autouse=True)
async def dispose_database_engine_between_retry_tests() -> None:
    """Avoid reusing an asyncpg connection across pytest event loops."""
    yield
    from app.database.session import engine

    await engine.dispose()


async def _create_workflow(session, user_id: int, step: dict) -> str:
    workflow = await WorkflowService(session).create(
        user_id=user_id,
        name="Retry test workflow",
        steps=[step],
    )
    return workflow.id


def _read_step(*, max_retries: int = 2) -> dict:
    return {
        "name": "Read project status",
        "step_type": "connector",
        "connector_id": "mcp",
        "operation": "project_status",
        "arguments": {},
        "access_type": "read",
        "max_retries": max_retries,
    }


@pytest.mark.asyncio
async def test_read_connector_retries_and_persists_count(test_user, monkeypatch) -> None:
    from app.database.session import AsyncSessionFactory

    calls = 0

    async def transient_execute(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ConnectorResult(
                connector_id="mcp",
                operation="project_status",
                status="error",
                error=ConnectorErrorDetail(
                    code="connector_execution_failed",
                    message="Temporary local failure",
                ),
            )
        return ConnectorResult(
            connector_id="mcp",
            operation="project_status",
            status="success",
            data={"status": "ok"},
        )

    monkeypatch.setattr("app.workflows.executor.ConnectorExecutor.execute", transient_execute)
    async with AsyncSessionFactory() as session:
        workflow_id = await _create_workflow(session, test_user.id, _read_step(max_retries=2))
        workflow = await WorkflowExecutor(session).run(
            workflow_id=workflow_id, user_id=test_user.id, role="user"
        )
        steps = await WorkflowService(session).steps(workflow_id=workflow_id, user_id=test_user.id)

        assert workflow is not None and workflow.status == "completed"
        assert calls == 2
        assert steps[0].status == "completed"
        assert steps[0].retry_count == 1
        assert steps[0].max_retries == 2

    async with AsyncSessionFactory() as reloaded_session:
        reloaded = await WorkflowService(reloaded_session).steps(
            workflow_id=workflow_id, user_id=test_user.id
        )
        assert reloaded[0].retry_count == 1


@pytest.mark.asyncio
async def test_tool_transient_failure_retries(test_user, monkeypatch) -> None:
    from app.database.session import AsyncSessionFactory

    calls = 0

    async def transient_execute(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ToolResult(
                tool_name="current_time",
                status="error",
                error=ToolErrorDetail(
                    code="tool_execution_failed", message="Temporary local failure"
                ),
            )
        return ToolResult(tool_name="current_time", status="success", output={"utc": "ok"})

    monkeypatch.setattr("app.workflows.executor.ToolExecutor.execute", transient_execute)
    async with AsyncSessionFactory() as session:
        workflow_id = await _create_workflow(
            session,
            test_user.id,
            {
                "name": "Get current time",
                "step_type": "tool",
                "tool_name": "current_time",
                "arguments": {"tool_name": "current_time", "input": {}},
                "max_retries": 1,
            },
        )
        workflow = await WorkflowExecutor(session).run(
            workflow_id=workflow_id, user_id=test_user.id, role="user"
        )
        steps = await WorkflowService(session).steps(workflow_id=workflow_id, user_id=test_user.id)

    assert workflow is not None and workflow.status == "completed"
    assert calls == 2
    assert steps[0].retry_count == 1


@pytest.mark.asyncio
async def test_knowledge_transient_failure_retries(test_user, monkeypatch) -> None:
    from app.database.session import AsyncSessionFactory

    calls = 0

    async def transient_search(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise KnowledgeError("Temporary embedding provider failure")
        return []

    monkeypatch.setattr(KnowledgeService, "search", transient_search)
    async with AsyncSessionFactory() as session:
        workflow_id = await _create_workflow(
            session,
            test_user.id,
            {
                "name": "Search knowledge",
                "step_type": "knowledge",
                "arguments": {"query": "Phoenix"},
                "max_retries": 1,
            },
        )
        workflow = await WorkflowExecutor(session).run(
            workflow_id=workflow_id, user_id=test_user.id, role="user"
        )
        steps = await WorkflowService(session).steps(workflow_id=workflow_id, user_id=test_user.id)

    assert workflow is not None and workflow.status == "completed"
    assert calls == 2
    assert steps[0].retry_count == 1


@pytest.mark.asyncio
async def test_exhausted_read_retries_fail_workflow(test_user, monkeypatch) -> None:
    from app.database.session import AsyncSessionFactory

    async def always_fail(self, **kwargs):
        return ConnectorResult(
            connector_id="mcp",
            operation="project_status",
            status="error",
            error=ConnectorErrorDetail(
                code="connector_execution_failed", message="Temporary local failure"
            ),
        )

    monkeypatch.setattr("app.workflows.executor.ConnectorExecutor.execute", always_fail)
    async with AsyncSessionFactory() as session:
        workflow_id = await _create_workflow(session, test_user.id, _read_step(max_retries=1))
        workflow = await WorkflowExecutor(session).run(
            workflow_id=workflow_id, user_id=test_user.id, role="user"
        )
        steps = await WorkflowService(session).steps(workflow_id=workflow_id, user_id=test_user.id)

    assert workflow is not None and workflow.status == "failed"
    assert steps[0].status == "failed"
    assert steps[0].retry_count == 1


@pytest.mark.asyncio
async def test_non_retryable_failures_do_not_consume_retries(test_user, monkeypatch) -> None:
    from app.database.session import AsyncSessionFactory

    async def denied_execute(self, **kwargs):
        return ConnectorResult(
            connector_id="mcp",
            operation="project_status",
            status="error",
            error=ConnectorErrorDetail(code="connector_not_authorized", message="Not authorized"),
        )

    monkeypatch.setattr("app.workflows.executor.ConnectorExecutor.execute", denied_execute)
    async with AsyncSessionFactory() as session:
        workflow_id = await _create_workflow(session, test_user.id, _read_step(max_retries=2))
        workflow = await WorkflowExecutor(session).run(
            workflow_id=workflow_id, user_id=test_user.id, role="user"
        )
        steps = await WorkflowService(session).steps(workflow_id=workflow_id, user_id=test_user.id)

    assert workflow is not None and workflow.status == "failed"
    assert steps[0].retry_count == 0


@pytest.mark.asyncio
async def test_empty_knowledge_query_does_not_retry(test_user) -> None:
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        workflow_id = await _create_workflow(
            session,
            test_user.id,
            {"name": "Search", "step_type": "knowledge", "arguments": {}, "max_retries": 2},
        )
        workflow = await WorkflowExecutor(session).run(
            workflow_id=workflow_id, user_id=test_user.id, role="user"
        )
        steps = await WorkflowService(session).steps(workflow_id=workflow_id, user_id=test_user.id)

    assert workflow is not None and workflow.status == "failed"
    assert steps[0].retry_count == 0


@pytest.mark.asyncio
async def test_write_steps_are_gated_without_retry(test_user) -> None:
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        workflow_id = await _create_workflow(
            session,
            test_user.id,
            {
                "name": "Create draft",
                "step_type": "connector",
                "connector_id": "local_email",
                "operation": "create_draft",
                "arguments": {
                    "to": "manager@example.com",
                    "subject": "Phoenix",
                    "body": "Ready",
                },
                "access_type": "write",
                "max_retries": 2,
            },
        )
        workflow = await WorkflowExecutor(session).run(
            workflow_id=workflow_id, user_id=test_user.id, role="user"
        )
        steps = await WorkflowService(session).steps(workflow_id=workflow_id, user_id=test_user.id)

    assert workflow is not None and workflow.status == "waiting_for_approval"
    assert steps[0].status == "waiting_for_approval"
    assert steps[0].retry_count == 0


@pytest.mark.parametrize(
    ("step_type", "access_type", "code"),
    [
        ("connector", "read", "connector_not_found"),
        ("tool", None, "tool_not_found"),
        ("connector", "write", "connector_execution_failed"),
        ("connector", "destructive", "connector_execution_failed"),
        ("knowledge", None, "knowledge_query_invalid"),
    ],
)
async def test_retry_classifier_excludes_unknown_and_unsafe_failures(
    step_type: str, access_type: str | None, code: str
) -> None:
    assert not is_retryable_workflow_failure(
        step_type=step_type, access_type=access_type, code=code
    )
