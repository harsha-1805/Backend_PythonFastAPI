"""Add bugs.previous_assignee_id for the Reopen workflow

Reopen needs to hand a bug back to whoever was actually working on it
(the developer) rather than the QA reporter it gets auto-reassigned to
on the ->Resolved transition. This column snapshots that "previous"
assignee at the moment a bug is marked Resolved, so
bug_service.reopen_bug can reassign to it later.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bugs",
        sa.Column("previous_assignee_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bugs", "previous_assignee_id")
