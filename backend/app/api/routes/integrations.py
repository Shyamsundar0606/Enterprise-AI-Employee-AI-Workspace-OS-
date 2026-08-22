"""Authenticated connector discovery and controlled direct execution."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db_session
from app.integrations.executor import ConnectorExecutor
from app.integrations.registry import ConnectorRegistry, get_connector_registry
from app.integrations.schemas import (
    ConnectorContext,
    ConnectorInfo,
    ConnectorRequest,
    ConnectorResult,
)
from app.models.integration_audit import IntegrationAuditEvent
from app.models.user import User

router = APIRouter(prefix="/integrations", tags=["integrations"])


def get_registry() -> ConnectorRegistry:
    return get_connector_registry()


@router.get("", response_model=list[ConnectorInfo])
async def list_connectors(
    _: Annotated[User, Depends(get_current_user)],
    registry: Annotated[ConnectorRegistry, Depends(get_registry)],
) -> list[ConnectorInfo]:
    return registry.list()


@router.get("/audit", response_model=list[dict])
async def list_audit(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    records = (
        await session.scalars(
            select(IntegrationAuditEvent)
            .where(IntegrationAuditEvent.user_id == current_user.id)
            .order_by(IntegrationAuditEvent.id.desc())
            .limit(100)
        )
    ).all()
    return [
        {
            "connector_id": item.connector_id,
            "operation": item.operation,
            "access_type": item.access_type,
            "status": item.status,
            "approval_required": item.approval_required,
            "request_id": item.request_id,
            "metadata": item.safe_metadata,
            "created_at": item.created_at,
        }
        for item in records
    ]


@router.get("/{connector_id}", response_model=ConnectorInfo)
async def get_connector(
    connector_id: str,
    _: Annotated[User, Depends(get_current_user)],
    registry: Annotated[ConnectorRegistry, Depends(get_registry)],
) -> ConnectorInfo:
    return next(item for item in registry.list() if item.id == connector_id)


@router.get("/{connector_id}/capabilities", response_model=list)
async def connector_capabilities(
    connector_id: str,
    _: Annotated[User, Depends(get_current_user)],
    registry: Annotated[ConnectorRegistry, Depends(get_registry)],
) -> list:
    return list(registry.get(connector_id).capabilities)


@router.post("/{connector_id}/execute", response_model=ConnectorResult)
async def execute_connector(
    connector_id: str,
    request: ConnectorRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> ConnectorResult:
    return await ConnectorExecutor(session=session).execute(
        connector_id=connector_id,
        operation=request.operation,
        raw_arguments=request.arguments,
        context=ConnectorContext(
            authenticated_user_id=current_user.id,
            role=current_user.role,
            conversation_id=request.conversation_id,
            request_id=request_id,
        ),
    )
