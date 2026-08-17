"""Deterministic local calendar connector."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.integrations.base import BaseConnector
from app.integrations.exceptions import ConnectorOperationError
from app.integrations.schemas import AccessType, ConnectorCapability, ConnectorContext, EmptyInput


class EventInput(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)


class QueryInput(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class LocalCalendarConnector(BaseConnector):
    id = "local_calendar"
    name = "Local Calendar"
    description = "Safe, deterministic calendar data scoped to the authenticated user."

    @property
    def capabilities(self) -> tuple[ConnectorCapability, ...]:
        return (
            ConnectorCapability(name="list_events", description="List upcoming events", access_type=AccessType.READ, input_schema={}),
            ConnectorCapability(name="get_event", description="Read one calendar event", access_type=AccessType.READ, input_schema=EventInput.model_json_schema()),
            ConnectorCapability(name="search_events", description="Search calendar events", access_type=AccessType.READ, input_schema=QueryInput.model_json_schema()),
            ConnectorCapability(name="create_event", description="Create calendar event", access_type=AccessType.WRITE, input_schema={}),
            ConnectorCapability(name="delete_event", description="Delete calendar event", access_type=AccessType.DESTRUCTIVE, input_schema=EventInput.model_json_schema()),
        )

    def input_model(self, operation: str) -> type[BaseModel]:
        models = {"list_events": EmptyInput, "get_event": EventInput, "search_events": QueryInput, "create_event": EmptyInput, "delete_event": EventInput}
        if operation not in models:
            self._invalid(operation)
        return models[operation]

    @staticmethod
    def _invalid(operation: str) -> type[BaseModel]:
        raise ConnectorOperationError(f"Operation is not supported: {operation}")

    async def health(self) -> bool:
        return True

    async def execute(self, *, operation: str, input_data: BaseModel, context: ConnectorContext) -> dict[str, Any]:
        events = self._events(context.authenticated_user_id)
        if operation == "list_events":
            return {"events": events}
        if operation == "get_event":
            event = next((item for item in events if item["id"] == input_data.event_id), None)
            if event is None:
                raise ConnectorOperationError("Event was not found in your calendar")
            return {"event": event}
        if operation == "search_events":
            return {"events": [item for item in events if input_data.query.lower() in str(item).lower()]}
        raise ConnectorOperationError("Operation cannot be executed automatically")

    @staticmethod
    def _events(user_id: int) -> list[dict[str, str]]:
        return [{"id": "phoenix-standup", "title": "Project Phoenix standup", "starts_at": "2026-08-18T09:30:00Z", "owner": f"user-{user_id}"}, {"id": "security-review", "title": "Security review", "starts_at": "2026-08-18T14:00:00Z", "owner": f"user-{user_id}"}]
