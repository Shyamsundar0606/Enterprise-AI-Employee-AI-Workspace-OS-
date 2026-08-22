"""Add workflow step dependencies.

Revision ID: 20260817_workflow_dependencies
Revises: 20260817_workflow_step_retries
"""

import sqlalchemy as sa
from alembic import op

revision = "20260817_workflow_dependencies"
down_revision = "20260817_workflow_step_retries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_steps",
        sa.Column("depends_on", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.alter_column("workflow_steps", "depends_on", server_default=None)


def downgrade() -> None:
    op.drop_column("workflow_steps", "depends_on")
