"""Ownership-safe workflow persistence, validation, and approval gating."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.integrations.redaction import redact
from app.integrations.registry import get_connector_registry
from app.models.workflow import (
    ApprovalRequest,
    Workflow,
    WorkflowAuditEvent,
    WorkflowStatus,
    WorkflowStep,
)
from app.tools.registry import get_tool_registry
from app.workflows.state_machine import require_workflow_transition


class WorkflowValidationError(ValueError):
    pass


class WorkflowService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def create(self, *, user_id: int, name: str, steps: list[dict[str, Any]]) -> Workflow:
        self._validate(steps)
        workflow = Workflow(user_id=user_id, name=name)
        self.session.add(workflow)
        await self.session.flush()
        await self.record_event(workflow, "workflow_created")
        for position, item in enumerate(steps):
            arguments = dict(item.get("arguments", {}))
            if item["step_type"] == "tool":
                arguments["tool_name"] = item["tool_name"]
            self.session.add(
                WorkflowStep(
                    workflow_id=workflow.id,
                    position=position,
                    name=item["name"],
                    step_type=item["step_type"],
                    connector_id=item.get("connector_id"),
                    operation=item.get("operation"),
                    arguments=arguments,
                    depends_on=item.get("depends_on", []),
                    access_type=item.get("access_type"),
                    requires_approval=bool(item.get("requires_approval", False)),
                    max_retries=int(item.get("max_retries", self.settings.workflow_max_retries)),
                )
            )
        await self.session.commit()
        return workflow

    async def record_event(
        self, workflow: Workflow, event_type: str, safe_metadata: dict[str, Any] | None = None
    ) -> None:
        self.session.add(
            WorkflowAuditEvent(
                workflow_id=workflow.id,
                user_id=workflow.user_id,
                event_type=event_type,
                safe_metadata=redact(safe_metadata or {}),
            )
        )
        await self.session.flush()

    async def get(self, *, workflow_id: str, user_id: int) -> Workflow | None:
        return await self.session.scalar(
            select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == user_id)
        )

    async def list(self, *, user_id: int) -> list[Workflow]:
        return list(
            (
                await self.session.scalars(
                    select(Workflow)
                    .where(Workflow.user_id == user_id)
                    .order_by(Workflow.created_at.desc())
                )
            ).all()
        )

    async def steps(self, *, workflow_id: str, user_id: int) -> list[WorkflowStep]:
        if await self.get(workflow_id=workflow_id, user_id=user_id) is None:
            return []
        return list(
            (
                await self.session.scalars(
                    select(WorkflowStep)
                    .where(WorkflowStep.workflow_id == workflow_id)
                    .order_by(WorkflowStep.position)
                )
            ).all()
        )

    async def gate_approval(self, *, workflow: Workflow, step: WorkflowStep) -> ApprovalRequest:
        require_workflow_transition(workflow.status, WorkflowStatus.WAITING_FOR_APPROVAL)
        arguments = redact(step.arguments)
        action_hash = self.action_hash(
            step.id, step.connector_id or "", step.operation or "", arguments
        )
        approval = ApprovalRequest(
            workflow_id=workflow.id,
            workflow_step_id=step.id,
            user_id=workflow.user_id,
            connector_id=step.connector_id or "",
            operation=step.operation or "",
            sanitized_arguments=arguments,
            action_hash=action_hash,
            risk_level="high" if step.access_type == "destructive" else "medium",
            expires_at=datetime.now(UTC) + timedelta(minutes=60),
        )
        workflow.status = WorkflowStatus.WAITING_FOR_APPROVAL.value
        step.status = WorkflowStatus.WAITING_FOR_APPROVAL.value
        self.session.add(approval)
        await self.record_event(workflow, "approval_requested", {"step_id": step.id})
        await self.session.commit()
        return approval

    async def cancel(self, *, workflow_id: str, user_id: int) -> Workflow | None:
        workflow = await self.session.scalar(
            select(Workflow)
            .where(Workflow.id == workflow_id, Workflow.user_id == user_id)
            .with_for_update()
        )
        if workflow is None:
            return None
        if workflow.status not in {"pending", "running", "waiting_for_approval"}:
            raise WorkflowValidationError("Workflow cannot be cancelled")
        require_workflow_transition(workflow.status, WorkflowStatus.CANCELLED)
        workflow.status = WorkflowStatus.CANCELLED.value
        await self.record_event(workflow, "workflow_cancelled")
        for step in await self.steps(workflow_id=workflow_id, user_id=user_id):
            if step.status != "completed":
                step.status = "cancelled"
        approvals = await self.session.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.workflow_id == workflow_id, ApprovalRequest.status == "pending"
            )
        )
        for approval in approvals:
            approval.status = "cancelled"
        await self.session.commit()
        return workflow

    @staticmethod
    def action_hash(
        step_id: str, connector_id: str, operation: str, arguments: dict[str, Any]
    ) -> str:
        payload = json.dumps(
            {
                "step_id": step_id,
                "connector_id": connector_id,
                "operation": operation,
                "arguments": arguments,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _validate(self, steps: list[dict[str, Any]]) -> None:
        if not steps or len(steps) > 20:
            raise WorkflowValidationError("Workflow step count is invalid")
        dependencies: dict[int, list[int]] = {}
        for position, step in enumerate(steps):
            if step.get("step_type") not in {"connector", "tool", "knowledge"}:
                raise WorkflowValidationError("Workflow step type is not allowed")
            if len(json.dumps(step.get("arguments", {}))) > 50_000:
                raise WorkflowValidationError("Workflow arguments exceed the allowed size")
            depends_on = step.get("depends_on", [])
            if not isinstance(depends_on, list) or any(
                isinstance(item, bool) or not isinstance(item, int) or item < 0 or item >= position
                for item in depends_on
            ):
                raise WorkflowValidationError("Workflow dependencies are invalid")
            dependencies[position] = depends_on
            max_retries = step.get("max_retries", self.settings.workflow_max_retries)
            if (
                isinstance(max_retries, bool)
                or not isinstance(max_retries, int)
                or max_retries < 0
                or max_retries > self.settings.workflow_max_retries
            ):
                raise WorkflowValidationError("Workflow retry limit is invalid")
            if step["step_type"] == "connector":
                connector = get_connector_registry().get(step.get("connector_id", ""))
                if not any(
                    capability.name == step.get("operation")
                    for capability in connector.capabilities
                ):
                    raise WorkflowValidationError("Workflow connector operation is not allowed")
            if step["step_type"] == "tool":
                get_tool_registry().get(step.get("tool_name", ""))
        visiting: set[int] = set()
        visited: set[int] = set()

        def visit(position: int) -> None:
            if position in visiting:
                raise WorkflowValidationError("Workflow dependencies contain a cycle")
            if position in visited:
                return
            visiting.add(position)
            for dependency in dependencies[position]:
                visit(dependency)
            visiting.remove(position)
            visited.add(position)

        for position in dependencies:
            visit(position)
