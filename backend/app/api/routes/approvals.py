"""Authenticated, owner-scoped approval decisions."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db_session
from app.models.user import User
from app.schemas.approval import ApprovalDecisionOut, ApprovalOut
from app.workflows.approvals import ApprovalService
from app.workflows.state_machine import InvalidWorkflowTransition

router = APIRouter(prefix="/approvals", tags=["approvals"])


def out(item) -> ApprovalOut:
    return ApprovalOut(
        id=item.id,
        workflow_id=item.workflow_id,
        workflow_step_id=item.workflow_step_id,
        status=item.status,
        connector_id=item.connector_id,
        operation=item.operation,
        sanitized_arguments=item.sanitized_arguments,
        risk_level=item.risk_level,
        expires_at=item.expires_at,
        decided_at=item.decided_at,
    )


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ApprovalOut]:
    return [out(item) for item in await ApprovalService(session).list_pending(current_user.id)]


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_approval(
    approval_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalOut:
    approval = await ApprovalService(session).get(approval_id, current_user.id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return out(approval)


@router.post("/{approval_id}/approve", response_model=ApprovalDecisionOut)
async def approve(
    approval_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalDecisionOut:
    service = ApprovalService(session)
    try:
        workflow = await service.approve_and_execute(
            approval_id, current_user.id, current_user.role
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Approval not found") from exc
    except InvalidWorkflowTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    approval = await service.get(approval_id, current_user.id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return ApprovalDecisionOut(
        approval=out(approval),
        workflow_id=workflow.id if workflow else None,
        workflow_status=workflow.status if workflow else None,
    )


@router.post("/{approval_id}/reject", response_model=ApprovalDecisionOut)
async def reject(
    approval_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalDecisionOut:
    try:
        approval = await ApprovalService(session).reject(approval_id, current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Approval not found") from exc
    except InvalidWorkflowTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApprovalDecisionOut(
        approval=out(approval), workflow_id=approval.workflow_id, workflow_status="cancelled"
    )
