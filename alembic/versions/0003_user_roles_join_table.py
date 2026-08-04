"""user_roles many-to-many join table (replaces users.role_id)

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- user_roles (matches USER_ROLES in the ER diagram) ---------------
    op.create_table(
        "user_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("assigned_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )
    op.create_index("ix_user_roles_id", "user_roles", ["id"])

    # --- migrate existing single-role data (if any) into the join table --
    # `users.role_id` only exists on databases that ran migration 0001/0002
    # before this one. Using SQLAlchemy's inspector (rather than a raw
    # `information_schema.columns` query, which is Postgres-specific and
    # breaks on SQLite) keeps this migration portable across both.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}
    if "role_id" in existing_columns:
        conn.execute(
            sa.text(
                "INSERT INTO user_roles (user_id, role_id, assigned_at) "
                "SELECT id, role_id, CURRENT_TIMESTAMP FROM users WHERE role_id IS NOT NULL"
            )
        )
        # batch_alter_table: on Postgres this is just a plain ALTER TABLE
        # DROP COLUMN; on SQLite (which can't drop a column that's part of
        # an FK constraint without recreating the table) it transparently
        # does that table-rebuild for us. Same call works on both.
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("role_id")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="SET NULL"), nullable=True),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE users SET role_id = ur.role_id "
            "FROM (SELECT DISTINCT ON (user_id) user_id, role_id FROM user_roles "
            "ORDER BY user_id, assigned_at DESC) ur "
            "WHERE users.id = ur.user_id"
        )
    )
    op.drop_index("ix_user_roles_id", table_name="user_roles")
    op.drop_table("user_roles")
