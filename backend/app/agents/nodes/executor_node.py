from app.agents.executor import ExecutionExecutor
from app.agents.registry import AgentRegistry
from app.agents.state import AgentState
from app.tools.schemas import ToolContext, ToolErrorDetail, ToolResult


async def executor_node(state: AgentState, executor: ExecutionExecutor) -> AgentState:
    plan = state["plan"]
    selected_tool = state["selected_tool"]
    agent = AgentRegistry().get(state.get("selected_agent", "general"))
    if selected_tool != "none" and selected_tool not in agent.allowed_tools:
        result = ToolResult(
            tool_name=selected_tool,
            status="error",
            error=ToolErrorDetail(
                code="agent_tool_not_authorized",
                message="Selected agent is not authorized to use this tool",
            ),
        )
        return {"tool_result": result.model_dump(mode="json")}
    result = await executor.execute(
        selected_tool=selected_tool,
        tool_input=plan.get("tool_input", {}),
        context=ToolContext(
            user_id=state["user_id"],
            role=state.get("user_role", "user"),
            conversation_id=state["conversation_id"],
        ),
    )
    return {"tool_result": result.model_dump(mode="json") if result else None}
