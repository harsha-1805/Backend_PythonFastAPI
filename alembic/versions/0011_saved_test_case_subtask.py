"""Add saved_test_cases.subtask_id

Lets a saved AI test case set be linked to a specific SubTask (in
addition to / instead of a Task via saved_test_cases.task_id or a Bug
via saved_test_cases.bug_id), so test cases generated for a subtask can
be saved and later filtered/retrieved by that subtask directly.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("saved_test_cases") as batch_op:
        batch_op.add_column(
            sa.Column(
                "subtask_id",
                sa.Integer(),
                sa.ForeignKey("subtasks.id", ondelete="CASCADE"),
                nullable=True,
            )
        )
    op.create_index("ix_saved_test_cases_subtask_id", "saved_test_cases", ["subtask_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_test_cases_subtask_id", table_name="saved_test_cases")
    with op.batch_alter_table("saved_test_cases") as batch_op:
        batch_op.drop_column("subtask_id")
