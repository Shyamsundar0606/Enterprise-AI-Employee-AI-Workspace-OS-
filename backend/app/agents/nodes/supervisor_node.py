"""LangGraph node for bounded supervisor delegation."""

from app.agents.state import AgentState
from app.agents.supervisor import Supervisor


async def supervisor_node(state: AgentState, supervisor: Supervisor) -> AgentState:
    return supervisor.coordinate(state)
