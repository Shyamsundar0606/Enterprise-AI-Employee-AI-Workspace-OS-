"""Base class for explicitly registered connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from app.integrations.schemas import ConnectorCapability, ConnectorContext


class BaseConnector(ABC):
    id: str
    name: str
    description: str
    requires_credentials: bool = False
    enabled: bool = True
    allowed_roles: frozenset[str] = frozenset({"user", "admin"})

    @property
    @abstractmethod
    def capabilities(self) -> tuple[ConnectorCapability, ...]:
        raise NotImplementedError

    @abstractmethod
    def input_model(self, operation: str) -> type[BaseModel]:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def execute(
        self, *, operation: str, input_data: BaseModel, context: ConnectorContext
    ) -> dict[str, Any]:
        raise NotImplementedError
