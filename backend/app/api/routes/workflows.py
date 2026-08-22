"""Authenticated workflow lifecycle endpoints."""

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db_session
from app.models.user import User
from app.models.workflow import WorkflowAuditEvent
from app.schemas.workflow import WorkflowCreate, WorkflowOut, WorkflowStepOut
from app.workflows.executor import WorkflowExecutor
from app.workflows.service import WorkflowService, WorkflowValidationError
from app.workflows.state_machine import InvalidWorkflowTransition

router = APIRouter(prefix="/workflows", tags=["workflows"])

_SAFE_WORKFLOW_SSE_EVENT_TYPES = frozenset(
    {
        "workflow_created",
        "workflow_started",
        "step_started",
        "step_completed",
        "step_failed",
        "approval_requested",
        "approval_approved",
        "approval_rejected",
        "approved_action_executed",
        "workflow_resumed",
        "workflow_cancelled",
        "workflow_completed",
        "workflow_failed",
    }
)
_SAFE_WORKFLOW_SSE_METADATA_KEYS = frozenset({"step_id", "approval_id"})


def out(workflow) -> WorkflowOut:
    return WorkflowOut(
        id=workflow.id,
        name=workflow.name,
        status=workflow.status,
        current_step=workflow.current_step,
    )


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    body: WorkflowCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkflowOut:
    try:
        workflow = await WorkflowService(session).create(
            user_id=current_user.id,
            name=body.name,
            steps=[step.model_dump(exclude_none=True) for step in body.steps],
        )
    except (ValueError, WorkflowValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return out(workflow)


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[WorkflowOut]:
    return [out(item) for item in await WorkflowService(session).list(user_id=current_user.id)]


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(
    workflow_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkflowOut:
    workflow = await WorkflowService(session).get(workflow_id=workflow_id, user_id=current_user.id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return out(workflow)


@router.get("/{workflow_id}/steps", response_model=list[WorkflowStepOut])
async def workflow_steps(
    workflow_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[WorkflowStepOut]:
    service = WorkflowService(session)
    if await service.get(workflow_id=workflow_id, user_id=current_user.id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return [
        WorkflowStepOut(
            id=item.id,
            position=item.position,
            name=item.name,
            step_type=item.step_type,
            status=item.status,
            result=item.result,
        )
        for item in await service.steps(workflow_id=workflow_id, user_id=current_user.id)
    ]


@router.post("/{workflow_id}/run", response_model=WorkflowOut)
async def run_workflow(
    workflow_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkflowOut:
    workflow = await WorkflowExecutor(session).run(
        workflow_id=workflow_id, user_id=current_user.id, role=current_user.role
    )
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return out(workflow)


@router.post("/{workflow_id}/resume", response_model=WorkflowOut)
async def resume_workflow(
    workflow_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkflowOut:
    try:
        workflow = await WorkflowExecutor(session).resume_workflow(
            workflow_id=workflow_id, user_id=current_user.id, role=current_user.role
        )
    except InvalidWorkflowTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return out(workflow)


@router.post("/{workflow_id}/cancel", response_model=WorkflowOut)
async def cancel_workflow(
    workflow_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkflowOut:
    try:
        workflow = await WorkflowService(session).cancel(
            workflow_id=workflow_id, user_id=current_user.id
        )
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return out(workflow)


@router.get("/{workflow_id}/events")
async def workflow_events(
    workflow_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StreamingResponse:
    if await WorkflowService(session).get(workflow_id=workflow_id, user_id=current_user.id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    records = list(
        (
            await session.scalars(
                select(WorkflowAuditEvent)
                .where(
                    WorkflowAuditEvent.workflow_id == workflow_id,
                    WorkflowAuditEvent.user_id == current_user.id,
                )
                .order_by(WorkflowAuditEvent.id)
            )
        ).all()
    )

    async def events() -> AsyncIterator[str]:
        for item in records:
            if item.event_type not in _SAFE_WORKFLOW_SSE_EVENT_TYPES:
                continue
            metadata = {
                key: value
                for key, value in (item.safe_metadata or {}).items()
                if key in _SAFE_WORKFLOW_SSE_METADATA_KEYS
            }
            payload = {"type": item.event_type, "metadata": metadata}
            yield f"event: workflow\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
