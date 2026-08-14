"""Add bugs.subtask_id

Lets a bug be linked to a specific SubTask (in addition to / instead of
a Task via bugs.task_id), so a bug found while testing a subtask can be
filed against that subtask directly.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bugs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "subtask_id",
                sa.Integer(),
                sa.ForeignKey("subtasks.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
    op.create_index("ix_bugs_subtask_id", "bugs", ["subtask_id"])


def downgrade() -> None:
    op.drop_index("ix_bugs_subtask_id", table_name="bugs")
    with op.batch_alter_table("bugs") as batch_op:
        batch_op.drop_column("subtask_id")
