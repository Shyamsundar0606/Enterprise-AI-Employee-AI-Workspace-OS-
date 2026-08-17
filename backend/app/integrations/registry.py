"""Static allow-list registry for enterprise connectors."""

from __future__ import annotations

from functools import lru_cache

from app.integrations.base import BaseConnector
from app.integrations.connectors.calendar import LocalCalendarConnector
from app.integrations.connectors.email import LocalEmailConnector
from app.integrations.connectors.github import GitHubMockConnector
from app.integrations.connectors.mcp import MockMCPConnector
from app.integrations.connectors.workspace import WorkspaceConnector
from app.integrations.exceptions import ConnectorNotFoundError
from app.integrations.schemas import ConnectorInfo


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, BaseConnector] = {}

    def register(self, connector: BaseConnector) -> None:
        if connector.id in self._connectors:
            raise ValueError(f"Connector is already registered: {connector.id}")
        self._connectors[connector.id] = connector

    def get(self, connector_id: str) -> BaseConnector:
        try:
            connector = self._connectors[connector_id]
        except KeyError as exc:
            raise ConnectorNotFoundError("Requested connector is not available") from exc
        if not connector.enabled:
            raise ConnectorNotFoundError("Requested connector is not available")
        return connector

    def list(self) -> list[ConnectorInfo]:
        return [
            ConnectorInfo(
                id=item.id,
                name=item.name,
                description=item.description,
                capabilities=list(item.capabilities),
                requires_credentials=item.requires_credentials,
                enabled=item.enabled,
            )
            for item in self._connectors.values()
            if item.enabled
        ]


@lru_cache(maxsize=1)
def get_connector_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    for connector in (
        LocalEmailConnector(),
        LocalCalendarConnector(),
        WorkspaceConnector(),
        GitHubMockConnector(),
        MockMCPConnector(),
    ):
        registry.register(connector)
    return registry
