"""Add persisted workflow step retry limits.

Revision ID: 20260817_workflow_step_retries
Revises: 20260817_workflow_tables
"""

import sqlalchemy as sa
from alembic import op

revision = "20260817_workflow_step_retries"
down_revision = "20260817_workflow_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_steps",
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
    )
    op.alter_column("workflow_steps", "max_retries", server_default=None)


def downgrade() -> None:
    op.drop_column("workflow_steps", "max_retries")
