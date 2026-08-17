"""Tests for bounded deterministic multi-agent delegation."""

import pytest
from app.agents.graph import build_graph
from app.agents.registry import AgentDefinition, AgentRegistry
from app.agents.state import create_initial_state
from app.agents.supervisor import Supervisor
from app.llm.schemas import LLMChatResponse


def _state(message: str, context: list[dict[str, object]] | None = None):
    state = create_initial_state(
        conversation_id="multi-agent-test",
        user_id=1,
        user_message=message,
        retrieved_context=context,
    )
    state["user_role"] = "user"
    return state


@pytest.mark.parametrize(
    ("message", "context", "expected"),
    [
        ("Hello!", None, ["general"]),
        ("What is 17% of 45000?", None, ["data"]),
        ("What does my uploaded policy document say?", None, ["knowledge"]),
        (
            "Compare my documents and calculate the difference.",
            [{"content": "budget 200000 euros"}],
            ["planner", "knowledge", "data"],
        ),
    ],
)
def test_supervisor_routes_specialists(
    message: str, context: list[dict[str, object]] | None, expected: list[str]
) -> None:
    result = Supervisor().coordinate(_state(message, context))
    assert [task["agent_name"] for task in result["agent_tasks"]] == expected
    assert result["delegation_count"] <= 4
    assert all("user_id" in task["context"] for task in result["agent_tasks"])


def test_registry_is_explicit_and_prevents_duplicates() -> None:
    registry = AgentRegistry()
    assert {agent.name for agent in registry.list()} == {
        "general",
        "knowledge",
        "data",
        "planner",
        "integration",
    }
    with pytest.raises(ValueError, match="already registered"):
        registry.register(AgentDefinition("general", "duplicate", ("x",), frozenset()))
    with pytest.raises(ValueError, match="not available"):
        registry.get("arbitrary")


def test_supervisor_caps_delegation_and_task_size(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = Supervisor()
    monkeypatch.setattr(supervisor.settings, "max_agent_delegations", 1)
    result = supervisor.coordinate(
        _state(
            "Compare my uploaded documents and calculate the difference.",
            [{"content": "200000 euros"}],
        )
    )
    assert result["delegation_count"] == 1
    assert result["agent_tasks"][0]["agent_name"] == "planner"


@pytest.mark.asyncio
async def test_graph_preserves_sources_and_uses_data_agent_calculator() -> None:
    class FakeLLM:
        async def chat(self, request):
            assert "30000" in request.message
            return LLMChatResponse(
                conversation_id=request.conversation_id,
                response="15% is 30000 euros.",
                provider="fake",
                model="fake",
            )

    result = await build_graph(FakeLLM()).ainvoke(
        _state(
            "What is 15% of that budget?",
            [{"content": "Project Phoenix budget is 200000 euros."}],
        )
    )
    assert result["selected_agent"] == "data"
    assert result["tool_result"]["output"] == {"result": 30000.0}
    assert result["delegation_count"] == 3
