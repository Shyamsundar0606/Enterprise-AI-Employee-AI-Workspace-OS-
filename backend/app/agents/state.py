"""State contracts for the single-agent LangGraph runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict


class AgentState(TypedDict, total=False):
    conversation_id: str
    user_id: int
    user_role: str
    user_message: str
    messages: list[dict[str, str]]
    conversation_history: list[dict[str, Any]]
    retrieved_context: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    selected_agent: str
    active_agent: str
    delegation_count: int
    step_count: int
    agent_tasks: list[dict[str, Any]]
    agent_results: list[dict[str, Any]]
    plan: dict[str, Any]
    selected_tool: str
    tool_result: dict[str, Any] | None
    integration_result: dict[str, Any] | None
    llm_response: str
    status: Literal["pending", "running", "completed", "failed"]
    metadata: dict[str, Any]
    started_at: str
    completed_at: str | None


def create_initial_state(
    *,
    conversation_id: str,
    user_id: int,
    user_message: str,
    conversation_history: list[dict[str, Any]] | None = None,
    retrieved_context: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> AgentState:
    """Create an isolated state object for one graph invocation."""
    state: AgentState = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "user_message": user_message,
        "messages": [{"role": "user", "content": user_message}],
        "conversation_history": conversation_history or [],
        "retrieved_context": retrieved_context or [],
        "sources": sources or [],
        "delegation_count": 0,
        "step_count": 0,
        "agent_tasks": [],
        "agent_results": [],
        "integration_result": None,
        "status": "pending",
        "metadata": {},
        "started_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
    }
    return state
