"""MCP-compatible local adapter; all server data is treated as untrusted."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.integrations.base import BaseConnector
from app.integrations.exceptions import ConnectorOperationError
from app.integrations.schemas import AccessType, ConnectorCapability, ConnectorContext, EmptyInput


class EchoInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ResourceInput(BaseModel):
    uri: str = Field(pattern=r"^workspace://(projects|policies)$")


class MockMCPConnector(BaseConnector):
    id = "mcp"
    name = "Local MCP Adapter"
    description = "MCP-compatible allow-listed mock tools and resources."

    @property
    def capabilities(self) -> tuple[ConnectorCapability, ...]:
        return (ConnectorCapability(name="echo", description="Echo safe text", access_type=AccessType.READ, input_schema=EchoInput.model_json_schema()), ConnectorCapability(name="summarize_text_metadata", description="Return text metadata", access_type=AccessType.READ, input_schema=EchoInput.model_json_schema()), ConnectorCapability(name="project_status", description="Read local project status", access_type=AccessType.READ, input_schema={}), ConnectorCapability(name="read_resource", description="Read an allow-listed resource", access_type=AccessType.READ, input_schema=ResourceInput.model_json_schema()))

    def input_model(self, operation: str) -> type[BaseModel]:
        models = {"echo": EchoInput, "summarize_text_metadata": EchoInput, "project_status": EmptyInput, "read_resource": ResourceInput}
        if operation not in models:
            self._invalid(operation)
        return models[operation]

    @staticmethod
    def _invalid(operation: str) -> type[BaseModel]:
        raise ConnectorOperationError(f"MCP capability is not allow-listed: {operation}")

    async def health(self) -> bool:
        return True

    async def execute(self, *, operation: str, input_data: BaseModel, context: ConnectorContext) -> dict[str, Any]:
        if operation == "echo":
            return {"text": input_data.text}
        if operation == "summarize_text_metadata":
            return {"characters": len(input_data.text), "words": len(input_data.text.split())}
        if operation == "project_status":
            return {"project": "Enterprise AI Employee", "status": "local mock status available"}
        if operation == "read_resource":
            return {"uri": input_data.uri, "content": {"workspace://projects": "Project Phoenix is active.", "workspace://policies": "Writes require explicit approval."}[input_data.uri]}
        raise ConnectorOperationError("MCP capability is not available")
