"""Add workflow lifecycle audit events.

Revision ID: 20260817_workflow_audit_events
Revises: 20260817_workflow_dependencies
"""

import sqlalchemy as sa
from alembic import op

revision = "20260817_workflow_audit_events"
down_revision = "20260817_workflow_dependencies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.String(36),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("safe_metadata", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_workflow_audit_events_workflow_id", "workflow_audit_events", ["workflow_id"]
    )
    op.create_index("ix_workflow_audit_events_user_id", "workflow_audit_events", ["user_id"])


def downgrade() -> None:
    op.drop_table("workflow_audit_events")
