"""Add subtasks table, audit_logs table, and bugs.image_url

Adds support for:
  - Task -> SubTask hierarchy (Project -> Sprint -> Task -> SubTask)
  - Audit Log module (tracks create/update/status-change/delete actions
    across Projects/Sprints/Tasks/SubTasks/Bugs)
  - Persisting the AI Bug Generator's uploaded screenshot so it can be
    previewed later wherever the bug is shown (bugs.image_url)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- bugs.image_url --------------------------------------------------
    with op.batch_alter_table("bugs") as batch_op:
        batch_op.add_column(sa.Column("image_url", sa.String(length=500), nullable=True))

    # --- subtasks ----------------------------------------------------------
    op.create_table(
        "subtasks",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_to",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="To Do"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_subtasks_task_id", "subtasks", ["task_id"])

    # --- audit_logs ----------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("actor_name", sa.String(length=120), nullable=True),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("entity_name", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("field_changed", sa.String(length=60), nullable=True),
        sa.Column("old_value", sa.String(length=255), nullable=True),
        sa.Column("new_value", sa.String(length=255), nullable=True),
        sa.Column(
            "project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_project_id", "audit_logs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_project_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_subtasks_task_id", table_name="subtasks")
    op.drop_table("subtasks")

    with op.batch_alter_table("bugs") as batch_op:
        batch_op.drop_column("image_url")
