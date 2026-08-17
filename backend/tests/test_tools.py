"""Security and integration tests for the allow-listed tool system."""

from __future__ import annotations

import importlib
import inspect
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from app.agents.graph import build_graph
from app.agents.schemas import AgentPlan
from app.agents.state import create_initial_state
from app.llm.schemas import LLMChatResponse
from app.tools.base import BaseTool
from app.tools.calculator import CalculatorInput, CalculatorOutput, CalculatorTool
from app.tools.current_time import CurrentTimeOutput
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolContext
from fastapi.testclient import TestClient
from pydantic import BaseModel


def _context(*, role: str = "user") -> ToolContext:
    return ToolContext(user_id=7, role=role, conversation_id="tool-test")


@pytest.mark.asyncio
async def test_calculator_executes_only_safe_arithmetic() -> None:
    result = await ToolExecutor().execute(
        tool_name="calculator",
        raw_input={"expression": "25 * 4 + 10"},
        context=_context(),
    )
    assert result.status == "success"
    assert result.output == {"result": 110}


@pytest.mark.asyncio
async def test_current_time_returns_structured_utc_data() -> None:
    result = await ToolExecutor().execute(
        tool_name="current_time", raw_input={"timezone": "UTC"}, context=_context()
    )
    assert result.status == "success"
    assert result.output is not None
    assert result.output["timezone"] == "UTC"
    assert result.output["utc_offset"] == "+0000"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('whoami')",
        "open('/etc/passwd')",
        "(1).__class__",
        "[item for item in range(10)]",
    ],
)
async def test_calculator_rejects_malicious_expressions(expression: str) -> None:
    result = await ToolExecutor().execute(
        tool_name="calculator",
        raw_input={"expression": expression},
        context=_context(),
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "tool_execution_error"


def test_calculator_never_uses_eval_or_exec() -> None:
    source = inspect.getsource(CalculatorTool)
    assert "eval(" not in source
    assert "exec(" not in source


@pytest.mark.asyncio
async def test_unknown_and_invalid_tools_return_safe_structured_errors() -> None:
    executor = ToolExecutor()
    unknown = await executor.execute(
        tool_name="shell", raw_input={"command": "whoami"}, context=_context()
    )
    invalid = await executor.execute(
        tool_name="calculator", raw_input={"expression": ""}, context=_context()
    )
    assert unknown.error is not None and unknown.error.code == "tool_not_found"
    assert invalid.error is not None and invalid.error.code == "tool_input_invalid"
    assert unknown.input["command"] == "whoami"


class AdminOnlyTool(BaseTool):
    name = "admin_only"
    description = "Test-only authorization tool"
    input_model = CalculatorInput
    output_model = CalculatorOutput
    allowed_roles = frozenset({"admin"})

    async def execute(
        self, *, context: ToolContext, input_data: CalculatorInput
    ) -> CalculatorOutput:
        del context, input_data
        return CalculatorOutput(result=1)


class BrokenOutputTool(BaseTool):
    name = "broken_output"
    description = "Test-only invalid output tool"
    input_model = CalculatorInput
    output_model = CalculatorOutput

    async def execute(self, *, context: ToolContext, input_data: CalculatorInput) -> BaseModel:
        del context, input_data
        return CurrentTimeOutput(datetime="now", timezone="UTC", utc_offset="+0000")


class FailingTool(BaseTool):
    name = "failing_tool"
    description = "Test-only failing tool"
    input_model = CalculatorInput
    output_model = CalculatorOutput

    async def execute(
        self, *, context: ToolContext, input_data: CalculatorInput
    ) -> CalculatorOutput:
        del context, input_data
        raise RuntimeError("internal detail must not escape")


@pytest.mark.asyncio
async def test_authorization_output_validation_and_exceptions_are_safe() -> None:
    registry = ToolRegistry()
    registry.register(AdminOnlyTool())
    registry.register(BrokenOutputTool())
    registry.register(FailingTool())
    executor = ToolExecutor(registry)

    unauthorized = await executor.execute(
        tool_name="admin_only", raw_input={"expression": "1"}, context=_context()
    )
    invalid_output = await executor.execute(
        tool_name="broken_output", raw_input={"expression": "1"}, context=_context()
    )
    failed = await executor.execute(
        tool_name="failing_tool", raw_input={"expression": "1"}, context=_context()
    )

    assert unauthorized.error is not None and unauthorized.error.code == "tool_not_authorized"
    assert invalid_output.error is not None and invalid_output.error.code == "tool_output_invalid"
    assert failed.error is not None and failed.error.code == "tool_execution_failed"
    assert "internal detail" not in failed.error.message


def test_registry_prevents_duplicates_and_lists_only_registered_tools() -> None:
    registry = ToolRegistry()
    calculator = CalculatorTool()
    registry.register(calculator)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(calculator)
    assert [item.name for item in registry.list()] == ["calculator"]


@pytest.mark.asyncio
async def test_agent_graph_continues_after_tool_result() -> None:
    class FakeLLMService:
        def __init__(self) -> None:
            self.prompt = ""

        async def chat(self, request):
            self.prompt = request.message
            return LLMChatResponse(
                conversation_id=request.conversation_id,
                response="The result is 110.",
                provider="fake",
                model="fake",
            )

    service = FakeLLMService()
    state = create_initial_state(
        conversation_id="tool-conversation",
        user_id=7,
        user_message="Calculate 25 * 4 + 10",
    )
    state["user_role"] = "user"
    result = await build_graph(service).ainvoke(state)

    assert AgentPlan.model_validate(result["plan"]).tool_name == "calculator"
    assert result["tool_result"]["output"] == {"result": 110}
    assert "110" in service.prompt
    assert result["llm_response"] == "The result is 110."


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    db_path = tmp_path / "tools-test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"

    import app.config.settings as settings_module
    import app.database.redis as redis_module
    import app.database.session as session_module
    import app.main as main_module

    redis_module._redis_client = None
    settings_module.get_settings.cache_clear()
    importlib.reload(session_module)
    importlib.reload(main_module)
    with TestClient(main_module.app) as test_client:
        yield test_client


def _register_user(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "tools@example.com", "username": "toolsuser", "password": "secret123"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_tool_discovery_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/tools").status_code == 401
    token = _register_user(client)
    response = client.get("/api/v1/tools", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert {item["name"] for item in response.json()} == {"calculator", "current_time"}


def test_authenticated_agent_executes_calculator_tool(client: TestClient) -> None:
    """The API derives user context from JWT and returns the tool-assisted answer."""
    import app.api.v1.agents as agent_routes
    from app.agents.runtime import AgentRuntime

    class FakeLLMService:
        async def chat(self, request):
            assert "110" in request.message
            return LLMChatResponse(
                conversation_id=request.conversation_id,
                response="The result is 110.",
                provider="fake",
                model="fake",
            )

        async def stream(self, request):
            yield {"chunk": "The result is 110."}

        async def health(self):
            raise AssertionError("Health is not part of this test")

    original_dependency = agent_routes.get_agent_runtime
    client.app.dependency_overrides[original_dependency] = lambda: AgentRuntime(FakeLLMService())
    try:
        token = _register_user(client)
        response = client.post(
            "/api/v1/agents/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "conversation_id": "authenticated-tool-test",
                "message": "Calculate 25 * 4 + 10",
                "user_id": 9999,
            },
        )
    finally:
        client.app.dependency_overrides.pop(original_dependency, None)

    assert response.status_code == 200
    assert response.json()["response"] == "The result is 110."
    assert response.json()["tool_result"]["output"] == {"result": 110}


@pytest.mark.asyncio
async def test_sensitive_input_is_redacted_from_tool_results() -> None:
    result = await ToolExecutor().execute(
        tool_name="unknown",
        raw_input={"token": "not-for-persistence"},
        context=_context(),
    )
    assert result.input == {"token": "[REDACTED]"}
