"""Deterministic request-to-connector routing; never trusts model output."""

from __future__ import annotations

from app.integrations.schemas import ConnectorRequest


class IntegrationRouter:
    def select(self, message: str, conversation_id: str) -> ConnectorRequest | None:
        lower = message.lower()
        if "email" in lower or "emails" in lower or "mailbox" in lower:
            operation = (
                "send_email"
                if any(term in lower for term in ("send email", "send an email"))
                else "search_messages" if "about" in lower else "list_messages"
            )
            arguments = (
                {"query": message.split("about", 1)[1].strip()}
                if operation == "search_messages" and "about" in lower
                else {}
            )
            return ConnectorRequest(
                connector_id="local_email",
                operation=operation,
                arguments=arguments,
                conversation_id=conversation_id,
            )
        if "meeting" in lower or "calendar" in lower or "event" in lower:
            return ConnectorRequest(
                connector_id="local_calendar",
                operation="list_events",
                conversation_id=conversation_id,
            )
        if "github" in lower or "issue" in lower or "repository" in lower:
            return ConnectorRequest(
                connector_id="github_mock", operation="list_issues", conversation_id=conversation_id
            )
        if "mcp" in lower or "project status" in lower:
            return ConnectorRequest(
                connector_id="mcp", operation="project_status", conversation_id=conversation_id
            )
        return None
