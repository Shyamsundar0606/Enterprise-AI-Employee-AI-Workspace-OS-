import logging

from app.agents.planner import RequestPlanner
from app.agents.state import AgentState

logger = logging.getLogger(__name__)


async def planner_node(state: AgentState, planner: RequestPlanner) -> AgentState:
    plan = planner.create_plan(
        state["user_message"],
        retrieved_context=state.get("retrieved_context"),
    )
    logger.info(
        "Planner completed",
        extra={"conversation_id": state["conversation_id"], "plan": plan.model_dump()},
    )
    return {"plan": plan.model_dump(), "status": "running"}
