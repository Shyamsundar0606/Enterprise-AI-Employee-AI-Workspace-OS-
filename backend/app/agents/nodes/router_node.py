import logging

from app.agents.router import ExecutionRouter
from app.agents.schemas import AgentPlan
from app.agents.state import AgentState

logger = logging.getLogger(__name__)


async def router_node(state: AgentState, router: ExecutionRouter) -> AgentState:
    selected_tool = router.select(AgentPlan.model_validate(state["plan"]))
    logger.info(
        "Router selected execution route",
        extra={"conversation_id": state["conversation_id"], "selected_tool": selected_tool},
    )
    return {"selected_tool": selected_tool}
