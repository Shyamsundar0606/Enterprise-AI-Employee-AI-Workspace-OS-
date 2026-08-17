"""Authenticated discovery of explicitly registered safe tools."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.tools.registry import ToolRegistry, get_tool_registry
from app.tools.schemas import ToolInfo

router = APIRouter(prefix="/tools", tags=["tools"])


def get_registry() -> ToolRegistry:
    return get_tool_registry()


@router.get("", response_model=list[ToolInfo])
async def list_tools(
    _: Annotated[User, Depends(get_current_user)],
    registry: Annotated[ToolRegistry, Depends(get_registry)],
) -> list[ToolInfo]:
    """List public metadata for allow-listed tools only."""
    return registry.list()
