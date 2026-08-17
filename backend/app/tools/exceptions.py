"""Typed failures returned by the controlled tool execution layer."""


class ToolError(Exception):
    """Base class for expected tool execution failures."""

    code = "tool_error"


class ToolNotFoundError(ToolError):
    code = "tool_not_found"


class ToolAuthorizationError(ToolError):
    code = "tool_not_authorized"


class ToolExecutionError(ToolError):
    code = "tool_execution_error"
