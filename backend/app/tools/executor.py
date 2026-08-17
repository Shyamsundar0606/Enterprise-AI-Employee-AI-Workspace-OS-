"""Controlled validation and execution of registered tools."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from app.tools.exceptions import ToolAuthorizationError, ToolError
from app.tools.registry import ToolRegistry, get_tool_registry
from app.tools.schemas import ToolContext, ToolErrorDetail, ToolResult

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Runs only allow-listed tools with a trusted user context."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry or get_tool_registry()

    async def execute(
        self,
        *,
        tool_name: str,
        raw_input: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        sanitized_input = self._sanitize(raw_input)
        try:
            tool = self._registry.get(tool_name)
            if context.role not in tool.allowed_roles:
                raise ToolAuthorizationError("You are not authorized to use this tool")
        except ToolError as exc:
            return self._error(tool_name, sanitized_input, exc.code, str(exc))

        try:
            input_data = tool.input_model.model_validate(raw_input)
        except ValidationError:
            return self._error(
                tool_name,
                sanitized_input,
                "tool_input_invalid",
                "Tool input is invalid",
            )

        try:
            output_data = await tool.execute(context=context, input_data=input_data)
            output = tool.output_model.model_validate(output_data).model_dump(mode="json")
            return ToolResult(
                tool_name=tool_name,
                status="success",
                input=self._sanitize(input_data.model_dump(mode="json")),
                output=output,
            )
        except ValidationError:
            return self._error(
                tool_name,
                sanitized_input,
                "tool_output_invalid",
                "Tool output did not match its contract",
            )
        except ToolError as exc:
            return self._error(tool_name, sanitized_input, exc.code, str(exc))
        except Exception:
            logger.exception("Tool execution failed", extra={"tool_name": tool_name})
            return self._error(
                tool_name,
                sanitized_input,
                "tool_execution_failed",
                "Tool execution failed safely",
            )

    @staticmethod
    def _error(tool_name: str, input_data: dict[str, Any], code: str, message: str) -> ToolResult:
        return ToolResult(
            tool_name=tool_name,
            status="error",
            input=input_data,
            error=ToolErrorDetail(code=code, message=message),
        )

    @classmethod
    def _sanitize(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if cls._is_sensitive(key) else cls._sanitize(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._sanitize(item) for item in value]
        return value

    @staticmethod
    def _is_sensitive(key: str) -> bool:
        normalized = key.lower()
        return any(part in normalized for part in ("password", "secret", "token", "authorization"))
