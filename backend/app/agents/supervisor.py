"""Bounded deterministic supervisor for allow-listed specialist agents."""

from __future__ import annotations

import re
from uuid import uuid4

from app.agents.registry import AgentRegistry
from app.agents.schemas import AgentResult, AgentTask
from app.agents.state import AgentState
from app.config.settings import get_settings


class Supervisor:
    """Select specialists without letting model output control trusted context."""

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or AgentRegistry()
        self.settings = get_settings()

    def coordinate(self, state: AgentState) -> AgentState:
        names = self._select_agents(state["user_message"], state.get("retrieved_context", []))
        if not self.settings.multi_agent_enabled:
            names = ["general"]
        names = names[: self.settings.max_agent_delegations]
        tasks: list[AgentTask] = []
        results: list[AgentResult] = []
        for depth, name in enumerate(names):
            agent = self.registry.get(name)
            if not agent.enabled or state.get("user_role", "user") not in agent.allowed_roles:
                continue
            task = AgentTask(
                task_id=str(uuid4()),
                agent_name=agent.name,
                instruction=state["user_message"][: self.settings.max_agent_task_length],
                context={
                    "conversation_id": state["conversation_id"],
                    "user_id": state["user_id"],
                },
                allowed_tools=sorted(agent.allowed_tools),
                depth=depth,
            )
            tasks.append(task)
            results.append(
                AgentResult(
                    task_id=task.task_id,
                    agent_name=agent.name,
                    status="delegated",
                    metadata={"delegated_by": "supervisor"},
                )
            )
        selected = tasks[-1].agent_name if tasks else "general"
        return {
            "selected_agent": selected,
            "active_agent": selected,
            "delegation_count": len(tasks),
            "step_count": min(len(tasks), self.settings.max_agent_steps),
            "agent_tasks": [task.model_dump(mode="json") for task in tasks],
            "agent_results": [result.model_dump(mode="json") for result in results],
        }

    @staticmethod
    def _select_agents(message: str, context: list[dict[str, object]]) -> list[str]:
        lower = message.lower()
        if any(
            term in lower
            for term in (
                "email",
                "mailbox",
                "meeting",
                "calendar",
                "github",
                "issue",
                "mcp",
                "project status",
            )
        ):
            return ["integration"]
        knowledge = bool(context) or any(
            term in lower
            for term in ("document", "policy", "according to", "uploaded", "project phoenix")
        )
        data = bool(re.search(r"\bcalculate\b|\bdifference\b|\d+(?:\.\d+)?\s*[%*/+-]", lower))
        complex_task = (knowledge and data) or any(
            term in lower for term in ("compare", "summarize", "plan", "steps")
        )
        if complex_task:
            agents = ["planner"]
            if knowledge:
                agents.append("knowledge")
            if data:
                agents.append("data")
            return agents
        if data:
            return ["data"]
        if knowledge:
            return ["knowledge"]
        return ["general"]
