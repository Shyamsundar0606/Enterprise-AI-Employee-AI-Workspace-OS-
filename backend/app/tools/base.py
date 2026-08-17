"""Base type for allow-listed agent tools."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.tools.schemas import ToolContext


class BaseTool(ABC):
    """A tool can execute only after registry, validation, and authorization checks."""

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    allowed_roles: frozenset[str] = frozenset({"user", "admin"})

    @abstractmethod
    async def execute(self, *, context: ToolContext, input_data: BaseModel) -> BaseModel:
        """Execute a validated, authorized request."""
        raise NotImplementedError
