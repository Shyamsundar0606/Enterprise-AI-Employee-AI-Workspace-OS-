"""Registry for explicit, safe tool definitions."""

from __future__ import annotations

from functools import lru_cache

from app.tools.base import BaseTool
from app.tools.calculator import CalculatorTool
from app.tools.current_time import CurrentTimeTool
from app.tools.exceptions import ToolNotFoundError
from app.tools.schemas import ToolInfo


class ToolRegistry:
    """Owns the allow-list of tools available to the runtime."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool is already registered: {tool.name}")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> BaseTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError("Requested tool is not available") from exc

    def list(self) -> list[ToolInfo]:
        return [
            ToolInfo(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_model.model_json_schema(),
            )
            for tool in self._tools.values()
        ]


@lru_cache(maxsize=1)
def get_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(CurrentTimeTool())
    return registry
