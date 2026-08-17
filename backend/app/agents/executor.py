from typing import Any

from app.tools.executor import ToolExecutor
from app.tools.schemas import ToolContext, ToolResult


class ExecutionExecutor:
    """Bridges the existing LangGraph node to the controlled tool executor."""

    def __init__(self, tool_executor: ToolExecutor | None = None) -> None:
        self._tool_executor = tool_executor or ToolExecutor()

    async def execute(
        self,
        *,
        selected_tool: str,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult | None:
        if selected_tool == "none":
            return None
        return await self._tool_executor.execute(
            tool_name=selected_tool,
            raw_input=tool_input,
            context=context,
        )
