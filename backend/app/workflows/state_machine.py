"""Deterministic workflow transition rules."""

from app.models.workflow import ApprovalStatus, WorkflowStatus


class InvalidWorkflowTransition(ValueError):
    """Raised when immutable workflow state is moved illegally."""


_WORKFLOW_TRANSITIONS = {
    WorkflowStatus.PENDING: {WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED},
    WorkflowStatus.RUNNING: {
        WorkflowStatus.WAITING_FOR_APPROVAL,
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    },
    WorkflowStatus.WAITING_FOR_APPROVAL: {WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED},
    WorkflowStatus.COMPLETED: set(),
    WorkflowStatus.FAILED: set(),
    WorkflowStatus.CANCELLED: set(),
}


def require_workflow_transition(current: str, target: WorkflowStatus) -> None:
    if target not in _WORKFLOW_TRANSITIONS[WorkflowStatus(current)]:
        raise InvalidWorkflowTransition("Invalid workflow state transition")


def require_pending_approval(status: str) -> None:
    if ApprovalStatus(status) is not ApprovalStatus.PENDING:
        raise InvalidWorkflowTransition("Approval has already been decided")
