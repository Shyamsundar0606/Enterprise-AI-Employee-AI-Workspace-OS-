from app.agents.executor import ExecutionExecutor
from app.agents.state import AgentState


async def executor_node(state: AgentState, executor: ExecutionExecutor) -> AgentState:
    return {"tool_result": await executor.execute(state["selected_tool"])}
