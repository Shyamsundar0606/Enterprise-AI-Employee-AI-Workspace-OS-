"""Security tests for the Milestone 10 integration boundary."""

from pathlib import Path

import pytest
from app.integrations.connectors.workspace import WorkspaceConnector
from app.integrations.executor import ConnectorExecutor
from app.integrations.registry import ConnectorRegistry, get_connector_registry
from app.integrations.schemas import ConnectorContext


def context(user_id: int = 1, role: str = "user") -> ConnectorContext:
    return ConnectorContext(authenticated_user_id=user_id, role=role, conversation_id="test")


@pytest.mark.asyncio
async def test_registry_discovery_and_duplicate_prevention() -> None:
    registry = ConnectorRegistry()
    connector = WorkspaceConnector(Path("/tmp/integration-test-workspace"))
    registry.register(connector)
    with pytest.raises(ValueError):
        registry.register(connector)
    assert registry.get("workspace").id == "workspace"


@pytest.mark.asyncio
async def test_email_read_and_user_isolation() -> None:
    executor = ConnectorExecutor()
    first = await executor.execute(
        connector_id="local_email",
        operation="get_message",
        raw_arguments={"message_id": "phoenix-budget"},
        context=context(1),
    )
    second = await executor.execute(
        connector_id="local_email",
        operation="get_message",
        raw_arguments={"message_id": "phoenix-budget"},
        context=context(2),
    )
    assert first.status == second.status == "success"
    assert "user 1" in str(first.data)
    assert "user 1" not in str(second.data)


@pytest.mark.asyncio
async def test_write_and_destructive_operations_require_approval() -> None:
    executor = ConnectorExecutor()
    email = await executor.execute(
        connector_id="local_email",
        operation="send_email",
        raw_arguments={"to": "manager@local.test", "subject": "Ready", "body": "Report is ready"},
        context=context(),
    )
    calendar = await executor.execute(
        connector_id="local_calendar",
        operation="delete_event",
        raw_arguments={"event_id": "phoenix-standup"},
        context=context(),
    )
    assert email.status == calendar.status == "approval_required"
    assert email.requires_approval and calendar.requires_approval


@pytest.mark.asyncio
async def test_unknown_connector_operation_and_input_are_safe() -> None:
    executor = ConnectorExecutor()
    unknown = await executor.execute(
        connector_id="not_real", operation="read", raw_arguments={}, context=context()
    )
    operation = await executor.execute(
        connector_id="mcp", operation="shell", raw_arguments={}, context=context()
    )
    invalid = await executor.execute(
        connector_id="local_email", operation="get_message", raw_arguments={}, context=context()
    )
    assert unknown.error and unknown.error.code == "connector_not_found"
    assert operation.error and operation.error.code == "connector_operation_invalid"
    assert invalid.error and invalid.error.code == "connector_input_invalid"


@pytest.mark.asyncio
async def test_workspace_blocks_traversal_absolute_and_secrets(tmp_path: Path) -> None:
    registry = ConnectorRegistry()
    registry.register(WorkspaceConnector(tmp_path))
    executor = ConnectorExecutor(registry)
    for requested in ("../../.env", "C:/Windows/system.ini", ".env"):
        result = await executor.execute(
            connector_id="workspace",
            operation="read_text_file",
            raw_arguments={"path": requested},
            context=context(),
        )
        assert result.status == "error"
        assert result.error and result.error.code == "connector_operation_invalid"


@pytest.mark.asyncio
async def test_mcp_discovery_execution_and_secret_redaction() -> None:
    connector = get_connector_registry().get("mcp")
    assert {item.name for item in connector.capabilities} >= {"echo", "read_resource"}
    result = await ConnectorExecutor().execute(
        connector_id="mcp",
        operation="echo",
        raw_arguments={"text": "safe", "access_token": "never-return"},
        context=context(),
    )
    assert result.status == "success"
    assert result.data == {"text": "safe"}


@pytest.mark.asyncio
async def test_github_and_calendar_reads_are_scoped() -> None:
    executor = ConnectorExecutor()
    issues = await executor.execute(
        connector_id="github_mock", operation="list_issues", raw_arguments={}, context=context(4)
    )
    events = await executor.execute(
        connector_id="local_calendar", operation="list_events", raw_arguments={}, context=context(5)
    )
    assert "workspace-4" in str(issues.data)
    assert "user-5" in str(events.data)
