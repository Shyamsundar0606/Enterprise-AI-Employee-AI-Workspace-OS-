"""Local GitHub-shaped connector; no credential or network dependency."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.integrations.base import BaseConnector
from app.integrations.exceptions import ConnectorOperationError
from app.integrations.schemas import AccessType, ConnectorCapability, ConnectorContext, EmptyInput


class IssueInput(BaseModel):
    issue_number: int = Field(gt=0, le=999999)


class GitHubMockConnector(BaseConnector):
    id = "github_mock"
    name = "GitHub-style Local Connector"
    description = "Read-only simulated repository and issue data for the active user."

    @property
    def capabilities(self) -> tuple[ConnectorCapability, ...]:
        return (ConnectorCapability(name="list_repositories", description="List repositories", access_type=AccessType.READ, input_schema={}), ConnectorCapability(name="list_issues", description="List open issues", access_type=AccessType.READ, input_schema={}), ConnectorCapability(name="get_issue", description="Get an issue", access_type=AccessType.READ, input_schema=IssueInput.model_json_schema()), ConnectorCapability(name="create_issue", description="Create issue", access_type=AccessType.WRITE, input_schema={}), ConnectorCapability(name="close_issue", description="Close issue", access_type=AccessType.DESTRUCTIVE, input_schema=IssueInput.model_json_schema()))

    def input_model(self, operation: str) -> type[BaseModel]:
        models = {"list_repositories": EmptyInput, "list_issues": EmptyInput, "get_issue": IssueInput, "create_issue": EmptyInput, "close_issue": IssueInput}
        if operation not in models:
            self._invalid(operation)
        return models[operation]

    @staticmethod
    def _invalid(operation: str) -> type[BaseModel]:
        raise ConnectorOperationError(f"Operation is not supported: {operation}")

    async def health(self) -> bool:
        return True

    async def execute(self, *, operation: str, input_data: BaseModel, context: ConnectorContext) -> dict[str, Any]:
        repos = [{"name": f"workspace-{context.authenticated_user_id}", "private": True}]
        issues = [{"number": 1, "title": "Harden integration policy", "state": "open", "repository": repos[0]["name"]}]
        if operation == "list_repositories":
            return {"repositories": repos}
        if operation == "list_issues":
            return {"issues": issues}
        if operation == "get_issue":
            issue = next((item for item in issues if item["number"] == input_data.issue_number), None)
            if issue is None:
                raise ConnectorOperationError("Issue was not found")
            return {"issue": issue}
        raise ConnectorOperationError("Operation cannot be executed automatically")
