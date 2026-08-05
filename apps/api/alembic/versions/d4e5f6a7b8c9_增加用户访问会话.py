"""增加用户访问会话

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-05 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("user_access_visits"):
        return
    op.create_table(
        "user_access_visits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["user_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "user_id",
        "workspace_id",
        "session_id",
        "entry_type",
        "started_at",
        "last_activity_at",
        "ended_at",
        "end_reason",
    ):
        op.create_index(
            f"ix_user_access_visits_{column}", "user_access_visits", [column]
        )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("user_access_visits"):
        op.drop_table("user_access_visits")
