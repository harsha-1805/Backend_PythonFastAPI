"""Add bugs.task_id (assign a bug to a task) and tasks.sprint_id (scope a task to a sprint)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bugs") as batch_op:
        batch_op.add_column(
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
        )
        batch_op.create_index("ix_bugs_task_id", ["task_id"])

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(
            sa.Column("sprint_id", sa.Integer(), sa.ForeignKey("sprints.id", ondelete="SET NULL"), nullable=True)
        )
        batch_op.create_index("ix_tasks_sprint_id", ["sprint_id"])


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index("ix_tasks_sprint_id")
        batch_op.drop_column("sprint_id")

    with op.batch_alter_table("bugs") as batch_op:
        batch_op.drop_index("ix_bugs_task_id")
        batch_op.drop_column("task_id")
