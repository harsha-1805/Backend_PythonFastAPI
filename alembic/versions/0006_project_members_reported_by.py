"""Add project_members table, reported_by on tasks/subtasks

Adds support for:
  - Project team membership (project_members) — scopes which users can
    access a project and be assigned its tasks/bugs/subtasks
  - Task.reported_by / SubTask.reported_by — mirrors Bug.reported_by so
    every module has a consistent "assignee + reported by" pair

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_members",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "reported_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
            )
        )
    with op.batch_alter_table("subtasks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "reported_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
            )
        )

    # Backfill: every existing project's owner becomes its first team
    # member, so nobody who currently has access loses it the moment
    # this migration lands.
    op.execute(
        """
        INSERT INTO project_members (project_id, user_id, added_at)
        SELECT id, owner_id, NOW() FROM projects WHERE owner_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("subtasks") as batch_op:
        batch_op.drop_column("reported_by")
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("reported_by")

    op.drop_index("ix_project_members_user_id", table_name="project_members")
    op.drop_index("ix_project_members_project_id", table_name="project_members")
    op.drop_table("project_members")
