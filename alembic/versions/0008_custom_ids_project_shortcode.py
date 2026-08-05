"""Add custom_id to bugs/tasks/subtasks and shortcode to projects

Adds human-readable IDs derived from project shortcodes, e.g. a
project "Mumbai Development" gets shortcode "MD" and its bugs become
"MD-1", "MD-2"; tasks "MD-1T"; subtasks "MD-1T-1S".

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add shortcode to projects
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("shortcode", sa.String(length=10), nullable=True))

    # Add custom_id to bugs
    with op.batch_alter_table("bugs") as batch_op:
        batch_op.add_column(sa.Column("custom_id", sa.String(length=20), nullable=True))
    op.create_index("ix_bugs_custom_id", "bugs", ["custom_id"], unique=False)

    # Add custom_id to tasks
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("custom_id", sa.String(length=20), nullable=True))
    op.create_index("ix_tasks_custom_id", "tasks", ["custom_id"], unique=False)

    # Add custom_id to subtasks
    with op.batch_alter_table("subtasks") as batch_op:
        batch_op.add_column(sa.Column("custom_id", sa.String(length=25), nullable=True))
    op.create_index("ix_subtasks_custom_id", "subtasks", ["custom_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_subtasks_custom_id", table_name="subtasks")
    with op.batch_alter_table("subtasks") as batch_op:
        batch_op.drop_column("custom_id")

    op.drop_index("ix_tasks_custom_id", table_name="tasks")
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("custom_id")

    op.drop_index("ix_bugs_custom_id", table_name="bugs")
    with op.batch_alter_table("bugs") as batch_op:
        batch_op.drop_column("custom_id")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("shortcode")
