"""Add comments and notifications tables

Adds in-app commenting on Bugs/Tasks/SubTasks (polymorphic via
entity_type + entity_id, same pattern as audit_logs) and a
notifications table for the (previously-decorative) notification bell,
generated when someone comments on or is assigned an item.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_name", sa.String(120), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_comments_entity_type", "comments", ["entity_type"])
    op.create_index("ix_comments_entity_id", "comments", ["entity_id"])
    op.create_index("ix_comments_created_at", "comments", ["created_at"])
    # Composite index — every real query is "comments for this one entity,
    # newest first", so index the pair directly rather than relying on
    # the two single-column indexes above being combined efficiently.
    op.create_index("ix_comments_entity", "comments", ["entity_type", "entity_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("message", sa.String(255), nullable=False),
        sa.Column("link_path", sa.String(255), nullable=True),
        sa.Column("entity_type", sa.String(20), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    # Every real query is "this recipient's unread notifications, newest
    # first" — index the pair directly, same reasoning as comments above.
    op.create_index("ix_notifications_recipient_unread", "notifications", ["recipient_id", "is_read"])


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_unread", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_recipient_id", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_comments_entity", table_name="comments")
    op.drop_index("ix_comments_created_at", table_name="comments")
    op.drop_index("ix_comments_entity_id", table_name="comments")
    op.drop_index("ix_comments_entity_type", table_name="comments")
    op.drop_table("comments")
