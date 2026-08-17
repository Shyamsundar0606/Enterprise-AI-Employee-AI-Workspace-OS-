from app.agents.executor import ExecutionExecutor
from app.agents.state import AgentState
from app.tools.schemas import ToolContext


async def executor_node(state: AgentState, executor: ExecutionExecutor) -> AgentState:
    plan = state["plan"]
    result = await executor.execute(
        selected_tool=state["selected_tool"],
        tool_input=plan.get("tool_input", {}),
        context=ToolContext(
            user_id=state["user_id"],
            role=state.get("user_role", "user"),
            conversation_id=state["conversation_id"],
        ),
    )
    return {"tool_result": result.model_dump(mode="json") if result else None}
