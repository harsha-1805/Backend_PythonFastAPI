"""Add saved_test_cases table for persisting AI-generated test case sets

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_test_cases",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("bug_id", sa.Integer(), sa.ForeignKey("bugs.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("entity_type", sa.String(10), nullable=False),   # "task" | "bug"
        sa.Column("entity_title", sa.String(255), nullable=False),
        sa.Column("csv_data", sa.Text(), nullable=False),
        sa.Column("test_cases_json", sa.Text(), nullable=False),  # JSON array of rows
        sa.Column("saved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("saved_test_cases")
