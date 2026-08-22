"""One-time, snapshot-bound approval decisions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.schemas import ApprovedActionContext
from app.models.workflow import ApprovalRequest, ApprovalStatus, WorkflowStatus
from app.workflows.service import WorkflowService
from app.workflows.state_machine import (
    InvalidWorkflowTransition,
    require_pending_approval,
    require_workflow_transition,
)


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workflows = WorkflowService(session)

    async def list_pending(self, user_id: int) -> list[ApprovalRequest]:
        return list(
            (
                await self.session.scalars(
                    select(ApprovalRequest).where(
                        ApprovalRequest.user_id == user_id,
                        ApprovalRequest.status == ApprovalStatus.PENDING.value,
                    )
                )
            ).all()
        )

    async def get(self, approval_id: str, user_id: int) -> ApprovalRequest | None:
        return await self.session.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.id == approval_id, ApprovalRequest.user_id == user_id
            )
        )

    async def approve(self, approval_id: str, user_id: int) -> ApprovalRequest:
        approval = await self.session.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id, ApprovalRequest.user_id == user_id)
            .with_for_update()
        )
        if approval is None:
            raise LookupError("Approval was not found")
        require_pending_approval(approval.status)
        expires_at = (
            approval.expires_at.replace(tzinfo=UTC)
            if approval.expires_at.tzinfo is None
            else approval.expires_at
        )
        if expires_at <= datetime.now(UTC):
            approval.status = ApprovalStatus.EXPIRED.value
            await self.session.commit()
            raise InvalidWorkflowTransition("Approval has expired")
        workflow = await self.workflows.get(workflow_id=approval.workflow_id, user_id=user_id)
        steps = await self.workflows.steps(workflow_id=approval.workflow_id, user_id=user_id)
        step = next((item for item in steps if item.id == approval.workflow_step_id), None)
        if (
            workflow is None
            or step is None
            or workflow.status != WorkflowStatus.WAITING_FOR_APPROVAL.value
            or step.status != "waiting_for_approval"
        ):
            raise InvalidWorkflowTransition("Approval is no longer actionable")
        current_hash = self.workflows.action_hash(
            step.id, step.connector_id or "", step.operation or "", approval.sanitized_arguments
        )
        if current_hash != approval.action_hash or step.arguments != approval.sanitized_arguments:
            approval.status = ApprovalStatus.CANCELLED.value
            await self.session.commit()
            raise InvalidWorkflowTransition("Approved action has changed")
        approval.status = ApprovalStatus.APPROVED.value
        approval.decided_at = datetime.now(UTC)
        step.status = "approved"
        require_workflow_transition(workflow.status, WorkflowStatus.RUNNING)
        workflow.status = WorkflowStatus.RUNNING.value
        await self.workflows.record_event(
            workflow, "approval_approved", {"approval_id": approval.id}
        )
        await self.session.commit()
        return approval

    async def approve_and_execute(self, approval_id: str, user_id: int, role: str):
        """Consume a validated approval then execute only its immutable snapshot."""
        approval = await self.approve(approval_id, user_id)
        from app.workflows.executor import WorkflowExecutor

        return await WorkflowExecutor(self.session).execute_approved(
            workflow_id=approval.workflow_id,
            step_id=approval.workflow_step_id,
            user_id=user_id,
            role=role,
            approved=self.trusted_context(approval),
        )

    async def reject(self, approval_id: str, user_id: int) -> ApprovalRequest:
        approval = await self.session.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id, ApprovalRequest.user_id == user_id)
            .with_for_update()
        )
        if approval is None:
            raise LookupError("Approval was not found")
        require_pending_approval(approval.status)
        workflow = await self.workflows.get(workflow_id=approval.workflow_id, user_id=user_id)
        steps = await self.workflows.steps(workflow_id=approval.workflow_id, user_id=user_id)
        step = next((item for item in steps if item.id == approval.workflow_step_id), None)
        approval.status = ApprovalStatus.REJECTED.value
        approval.decided_at = datetime.now(UTC)
        if step is not None:
            step.status = "rejected"
        if workflow is not None:
            require_workflow_transition(workflow.status, WorkflowStatus.CANCELLED)
            workflow.status = WorkflowStatus.CANCELLED.value
            await self.workflows.record_event(
                workflow, "approval_rejected", {"approval_id": approval.id}
            )
        await self.session.commit()
        return approval

    @staticmethod
    def trusted_context(approval: ApprovalRequest) -> ApprovedActionContext:
        """Constructible only after `approve` has persisted the decision."""
        if approval.status != ApprovalStatus.APPROVED.value:
            raise InvalidWorkflowTransition("Approval has not been consumed")
        return ApprovedActionContext(
            approval_id=approval.id,
            workflow_id=approval.workflow_id,
            workflow_step_id=approval.workflow_step_id,
            authenticated_user_id=approval.user_id,
            action_hash=approval.action_hash,
        )
