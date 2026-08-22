"""Focused validation coverage for persisted workflow dependencies."""

import pytest
import pytest_asyncio
from app.integrations.schemas import ConnectorErrorDetail, ConnectorResult
from app.workflows.executor import WorkflowExecutor
from app.workflows.service import WorkflowService, WorkflowValidationError


@pytest_asyncio.fixture(autouse=True)
async def dispose_database_engine_between_dependency_tests() -> None:
    yield
    from app.database.session import engine

    await engine.dispose()


def _step(name: str, *, depends_on: list[int] | None = None) -> dict:
    return {
        "name": name,
        "step_type": "connector",
        "connector_id": "mcp",
        "operation": "project_status",
        "arguments": {},
        "depends_on": depends_on or [],
    }


@pytest.mark.asyncio
async def test_valid_prior_dependency_is_persisted(test_user) -> None:
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        workflow = await WorkflowService(session).create(
            user_id=test_user.id,
            name="Ordered reads",
            steps=[_step("First"), _step("Second", depends_on=[0])],
        )
        steps = await WorkflowService(session).steps(workflow_id=workflow.id, user_id=test_user.id)
    assert steps[1].depends_on == [0]


@pytest.mark.asyncio
@pytest.mark.parametrize("dependencies", ([2], [1], [-1]))
async def test_missing_self_or_forward_dependency_is_rejected(test_user, dependencies) -> None:
    from app.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        with pytest.raises(WorkflowValidationError):
            await WorkflowService(session).create(
                user_id=test_user.id,
                name="Invalid dependencies",
                steps=[_step("First", depends_on=dependencies)],
            )


@pytest.mark.asyncio
async def test_dependencies_execute_after_prerequisites(test_user, monkeypatch) -> None:
    from app.database.session import AsyncSessionFactory

    calls: list[str] = []

    async def execute(self, **kwargs):
        calls.append(kwargs["operation"])
        return ConnectorResult(
            connector_id="mcp", operation=kwargs["operation"], status="success", data={}
        )

    monkeypatch.setattr("app.workflows.executor.ConnectorExecutor.execute", execute)
    async with AsyncSessionFactory() as session:
        workflow = await WorkflowService(session).create(
            user_id=test_user.id,
            name="Ordered dependencies",
            steps=[_step("A"), _step("B", depends_on=[0])],
        )
        result = await WorkflowExecutor(session).run(
            workflow_id=workflow.id, user_id=test_user.id, role="user"
        )
        steps = await WorkflowService(session).steps(workflow_id=workflow.id, user_id=test_user.id)
    assert result is not None and result.status == "completed"
    assert calls == ["project_status", "project_status"]
    assert [item.status for item in steps] == ["completed", "completed"]


@pytest.mark.asyncio
async def test_failed_prerequisite_blocks_dependent_step(test_user, monkeypatch) -> None:
    from app.database.session import AsyncSessionFactory

    async def fail(self, **kwargs):
        return ConnectorResult(
            connector_id="mcp",
            operation="project_status",
            status="error",
            error=ConnectorErrorDetail(code="connector_not_authorized", message="Denied"),
        )

    monkeypatch.setattr("app.workflows.executor.ConnectorExecutor.execute", fail)
    async with AsyncSessionFactory() as session:
        workflow = await WorkflowService(session).create(
            user_id=test_user.id,
            name="Failed prerequisite",
            steps=[_step("A"), _step("B", depends_on=[0])],
        )
        result = await WorkflowExecutor(session).run(
            workflow_id=workflow.id, user_id=test_user.id, role="user"
        )
        steps = await WorkflowService(session).steps(workflow_id=workflow.id, user_id=test_user.id)
    assert result is not None and result.status == "failed"
    assert steps[0].status == "failed"
    assert steps[1].status == "pending"
