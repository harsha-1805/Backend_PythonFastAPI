"""Add Task.acceptance_criteria and task_attachments table

Supports the AI test-case generator: acceptance_criteria gives it a
distinct "what must be verified" signal separate from the free-form
description, and task_attachments lets a task carry reference
screenshots (design mocks / expected-result shots) that get sent to
Gemini alongside the text context for more accurate generated cases.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("acceptance_criteria", sa.Text(), nullable=True))

    op.create_table(
        "task_attachments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_url", sa.String(500), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_task_attachments_task_id", "task_attachments", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_task_attachments_task_id", table_name="task_attachments")
    op.drop_table("task_attachments")
    op.drop_column("tasks", "acceptance_criteria")
