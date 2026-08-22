"""Safe HTTP output for persisted approval requests."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ApprovalOut(BaseModel):
    id: str
    workflow_id: str
    workflow_step_id: str
    status: str
    connector_id: str
    operation: str
    sanitized_arguments: dict[str, Any]
    risk_level: str
    expires_at: datetime
    decided_at: datetime | None


class ApprovalDecisionOut(BaseModel):
    approval: ApprovalOut
    workflow_id: str | None = None
    workflow_status: str | None = None
