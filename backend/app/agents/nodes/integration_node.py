"""Executes deterministic, allow-listed integration reads for the graph."""

from app.agents.state import AgentState
from app.integrations.executor import ConnectorExecutor
from app.integrations.router import IntegrationRouter
from app.integrations.schemas import ConnectorContext


async def integration_node(state: AgentState, router: IntegrationRouter, executor: ConnectorExecutor) -> AgentState:
    request = router.select(state["user_message"], state["conversation_id"])
    if request is None:
        return {"integration_result": None}
    result = await executor.execute(connector_id=request.connector_id, operation=request.operation, raw_arguments=request.arguments, context=ConnectorContext(authenticated_user_id=state["user_id"], role=state.get("user_role", "user"), conversation_id=state["conversation_id"]))
    return {"integration_result": result.model_dump(mode="json")}
