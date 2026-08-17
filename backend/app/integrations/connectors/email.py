"""Deterministic, per-user local mailbox connector."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.integrations.base import BaseConnector
from app.integrations.exceptions import ConnectorOperationError
from app.integrations.schemas import AccessType, ConnectorCapability, ConnectorContext, EmptyInput


class MessageInput(BaseModel):
    message_id: str = Field(min_length=1, max_length=64)


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class DraftInput(BaseModel):
    to: str = Field(min_length=3, max_length=254)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10_000)


class LocalEmailConnector(BaseConnector):
    id = "local_email"
    name = "Local Email"
    description = "Safe, deterministic enterprise mailbox data scoped to the authenticated user."

    @property
    def capabilities(self) -> tuple[ConnectorCapability, ...]:
        return (
            ConnectorCapability(name="list_messages", description="List mailbox messages", access_type=AccessType.READ, input_schema={}),
            ConnectorCapability(name="get_message", description="Read one mailbox message", access_type=AccessType.READ, input_schema=MessageInput.model_json_schema()),
            ConnectorCapability(name="search_messages", description="Search mailbox messages", access_type=AccessType.READ, input_schema=SearchInput.model_json_schema()),
            ConnectorCapability(name="create_draft", description="Prepare an email draft", access_type=AccessType.WRITE, input_schema=DraftInput.model_json_schema()),
            ConnectorCapability(name="send_email", description="Send an external email", access_type=AccessType.WRITE, input_schema=DraftInput.model_json_schema()),
        )

    def input_model(self, operation: str) -> type[BaseModel]:
        models = {"list_messages": EmptyInput, "get_message": MessageInput, "search_messages": SearchInput, "create_draft": DraftInput, "send_email": DraftInput}
        if operation not in models:
            self._invalid(operation)
        return models[operation]

    @staticmethod
    def _invalid(operation: str) -> type[BaseModel]:
        raise ConnectorOperationError(f"Operation is not supported: {operation}")

    async def health(self) -> bool:
        return True

    async def execute(self, *, operation: str, input_data: BaseModel, context: ConnectorContext) -> dict[str, Any]:
        messages = self._messages(context.authenticated_user_id)
        if operation == "list_messages":
            return {"messages": [self._summary(item) for item in messages]}
        if operation == "get_message":
            message = next((item for item in messages if item["id"] == input_data.message_id), None)
            if message is None:
                raise ConnectorOperationError("Message was not found in your mailbox")
            return {"message": message}
        if operation == "search_messages":
            query = input_data.query.lower()
            return {"messages": [self._summary(item) for item in messages if query in str(item).lower()]}
        raise ConnectorOperationError("Operation cannot be executed automatically")

    @staticmethod
    def _summary(message: dict[str, str]) -> dict[str, str]:
        return {key: message[key] for key in ("id", "subject", "from", "received_at")}

    @staticmethod
    def _messages(user_id: int) -> list[dict[str, str]]:
        return [
            {"id": "phoenix-budget", "subject": "Project Phoenix Update", "from": "finance@local.test", "received_at": "2026-08-17T09:00:00Z", "body": f"Budget approval for user {user_id}: approved contingency is 10% of the Project Phoenix budget."},
            {"id": "security-review", "subject": "Security Review", "from": "security@local.test", "received_at": "2026-08-16T11:00:00Z", "body": f"Security review assigned to mailbox user {user_id}."},
            {"id": "weekly-engineering", "subject": "Weekly Engineering Report", "from": "engineering@local.test", "received_at": "2026-08-15T15:00:00Z", "body": "Engineering delivery remains on schedule."},
        ]
