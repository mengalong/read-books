"""增加日常记录与每日整理

Revision ID: c8d9e0f1a2b3
Revises: b3c4d5e6f7a8
Create Date: 2026-09-07 12:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "journal_captures",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("capture_type", sa.String(length=20), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_journal_captures_workspace_id", "journal_captures", ["workspace_id"])
    op.create_index("ix_journal_captures_created_by_user_id", "journal_captures", ["created_by_user_id"])
    op.create_index("ix_journal_captures_capture_type", "journal_captures", ["capture_type"])
    op.create_index("ix_journal_captures_local_date", "journal_captures", ["local_date"])
    op.create_index("ix_journal_captures_captured_at", "journal_captures", ["captured_at"])

    op.create_table(
        "journal_days",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("organization_status", sa.String(length=20), nullable=False),
        sa.Column("journal_text", sa.Text(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("organization_task_id", sa.String(length=36), nullable=True),
        sa.Column("organization_error", sa.Text(), nullable=True),
        sa.Column("organized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "local_date"),
    )
    op.create_index("ix_journal_days_workspace_id", "journal_days", ["workspace_id"])
    op.create_index("ix_journal_days_created_by_user_id", "journal_days", ["created_by_user_id"])
    op.create_index("ix_journal_days_local_date", "journal_days", ["local_date"])
    op.create_index("ix_journal_days_organization_status", "journal_days", ["organization_status"])
    op.create_index("ix_journal_days_organization_task_id", "journal_days", ["organization_task_id"])

    op.create_table(
        "journal_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_capture_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_journal_items_workspace_id", "journal_items", ["workspace_id"])
    op.create_index("ix_journal_items_created_by_user_id", "journal_items", ["created_by_user_id"])
    op.create_index("ix_journal_items_item_type", "journal_items", ["item_type"])
    op.create_index("ix_journal_items_status", "journal_items", ["status"])
    op.create_index("ix_journal_items_due_date", "journal_items", ["due_date"])


def downgrade() -> None:
    op.drop_index("ix_journal_items_due_date", table_name="journal_items")
    op.drop_index("ix_journal_items_status", table_name="journal_items")
    op.drop_index("ix_journal_items_item_type", table_name="journal_items")
    op.drop_index("ix_journal_items_created_by_user_id", table_name="journal_items")
    op.drop_index("ix_journal_items_workspace_id", table_name="journal_items")
    op.drop_table("journal_items")
    op.drop_index("ix_journal_days_organization_task_id", table_name="journal_days")
    op.drop_index("ix_journal_days_organization_status", table_name="journal_days")
    op.drop_index("ix_journal_days_local_date", table_name="journal_days")
    op.drop_index("ix_journal_days_created_by_user_id", table_name="journal_days")
    op.drop_index("ix_journal_days_workspace_id", table_name="journal_days")
    op.drop_table("journal_days")
    op.drop_index("ix_journal_captures_captured_at", table_name="journal_captures")
    op.drop_index("ix_journal_captures_local_date", table_name="journal_captures")
    op.drop_index("ix_journal_captures_capture_type", table_name="journal_captures")
    op.drop_index("ix_journal_captures_created_by_user_id", table_name="journal_captures")
    op.drop_index("ix_journal_captures_workspace_id", table_name="journal_captures")
    op.drop_table("journal_captures")
