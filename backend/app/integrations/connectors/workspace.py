"""Allow-listed per-user workspace connector with path confinement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.integrations.base import BaseConnector
from app.integrations.exceptions import ConnectorOperationError
from app.integrations.schemas import AccessType, ConnectorCapability, ConnectorContext, EmptyInput


class PathInput(BaseModel):
    path: str = Field(min_length=1, max_length=240)


class CreateFileInput(PathInput):
    content: str = Field(min_length=1, max_length=20_000)


class WorkspaceConnector(BaseConnector):
    id = "workspace"
    name = "Local Workspace"
    description = "A path-confined workspace containing only the authenticated user's files."

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or get_settings().workspace_connector_path

    @property
    def capabilities(self) -> tuple[ConnectorCapability, ...]:
        return (
            ConnectorCapability(name="list_files", description="List safe workspace files", access_type=AccessType.READ, input_schema={}),
            ConnectorCapability(name="get_file_metadata", description="Get safe file metadata", access_type=AccessType.READ, input_schema=PathInput.model_json_schema()),
            ConnectorCapability(name="read_text_file", description="Read a safe text file", access_type=AccessType.READ, input_schema=PathInput.model_json_schema()),
            ConnectorCapability(name="create_text_file", description="Create workspace file", access_type=AccessType.WRITE, input_schema=CreateFileInput.model_json_schema()),
            ConnectorCapability(name="delete_file", description="Delete workspace file", access_type=AccessType.DESTRUCTIVE, input_schema=PathInput.model_json_schema()),
        )

    def input_model(self, operation: str) -> type[BaseModel]:
        models = {"list_files": EmptyInput, "get_file_metadata": PathInput, "read_text_file": PathInput, "create_text_file": CreateFileInput, "delete_file": PathInput}
        if operation not in models:
            self._invalid(operation)
        return models[operation]

    @staticmethod
    def _invalid(operation: str) -> type[BaseModel]:
        raise ConnectorOperationError(f"Operation is not supported: {operation}")

    async def health(self) -> bool:
        return True

    async def execute(self, *, operation: str, input_data: BaseModel, context: ConnectorContext) -> dict[str, Any]:
        root = self._user_root(context.authenticated_user_id)
        root.mkdir(parents=True, exist_ok=True)
        sample = root / "project-status.txt"
        if not sample.exists():
            sample.write_text("Project Phoenix workspace status: active.", encoding="utf-8")
        if operation == "list_files":
            return {"files": [item.name for item in root.iterdir() if item.is_file() and self._safe_name(item.name)]}
        path = self._resolve(root, input_data.path)
        if operation == "get_file_metadata":
            if not path.is_file():
                raise ConnectorOperationError("Workspace file was not found")
            return {"name": path.name, "size": path.stat().st_size}
        if operation == "read_text_file":
            if not path.is_file():
                raise ConnectorOperationError("Workspace file was not found")
            return {"name": path.name, "content": path.read_text(encoding="utf-8")}
        raise ConnectorOperationError("Operation cannot be executed automatically")

    def _user_root(self, user_id: int) -> Path:
        return (self._root / str(user_id)).resolve()

    def _resolve(self, root: Path, requested: str) -> Path:
        raw = Path(requested)
        if raw.is_absolute() or ".." in raw.parts or not self._safe_name(raw.name):
            raise ConnectorOperationError("Workspace path is not allowed")
        candidate = (root / raw).resolve()
        if root not in candidate.parents or candidate.is_symlink():
            raise ConnectorOperationError("Workspace path is not allowed")
        return candidate

    @staticmethod
    def _safe_name(name: str) -> bool:
        return name not in {".env", ".env.local", "id_rsa", "credentials", "secrets"} and not name.startswith(".")
