from app.agents.exceptions import AgentRuntimeError


class ExecutionExecutor:
    """Executes an approved tool route; tools are intentionally unavailable in M5."""

    async def execute(self, selected_tool: str) -> str | None:
        if selected_tool == "none":
            return None
        raise AgentRuntimeError(f"Tool execution is not available: {selected_tool}")
