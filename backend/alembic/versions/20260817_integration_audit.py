"""Add integration audit events.

Revision ID: 20260817_integration_audit
Revises: 20260817_knowledge_tables
"""

import sqlalchemy as sa
from alembic import op

revision = "20260817_integration_audit"
down_revision = "20260817_knowledge_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("connector_id", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("access_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("safe_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_integration_audit_events_user_id", "integration_audit_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_integration_audit_events_user_id", table_name="integration_audit_events")
    op.drop_table("integration_audit_events")
