"""完善日常记录数据结构

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-08 09:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    day_columns = {column["name"] for column in inspector.get_columns("journal_days")}
    item_columns = {column["name"] for column in inspector.get_columns("journal_items")}
    if "model_consent" not in day_columns:
        op.add_column("journal_days", sa.Column("model_consent", sa.Boolean(), nullable=False, server_default=sa.true()))
    if "mood_score" not in day_columns:
        op.add_column("journal_days", sa.Column("mood_score", sa.Integer(), nullable=True))
    if "energy_score" not in day_columns:
        op.add_column("journal_days", sa.Column("energy_score", sa.Integer(), nullable=True))
    if "meaning_score" not in day_columns:
        op.add_column("journal_days", sa.Column("meaning_score", sa.Integer(), nullable=True))
    if "canonical_key" not in item_columns:
        op.add_column("journal_items", sa.Column("canonical_key", sa.String(length=240), nullable=True))
    item_indexes = {index["name"] for index in inspector.get_indexes("journal_items")}
    if "ix_journal_items_canonical_key" not in item_indexes:
        op.create_index("ix_journal_items_canonical_key", "journal_items", ["canonical_key"])
    if "review_status" not in item_columns:
        op.add_column("journal_items", sa.Column("review_status", sa.String(length=20), nullable=False, server_default="pending"))
    op.execute(
        """
        UPDATE journal_items
        SET review_status = CASE
            WHEN status IN ('done', 'completed') THEN 'completed'
            WHEN status IN ('dismissed', 'cancelled', 'archived') THEN 'cancelled'
            WHEN status IN ('open', 'inbox', 'added') THEN 'confirmed'
            ELSE 'pending'
        END
        """
    )
    if "ix_journal_items_review_status" not in {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("journal_items")
    }:
        op.create_index("ix_journal_items_review_status", "journal_items", ["review_status"])
    if not inspector.has_table("journal_day_versions"):
        op.create_table(
        "journal_day_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("journal_day_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("journal_text", sa.Text(), nullable=False),
        sa.Column("writing_style", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journal_day_id"], ["journal_days.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("journal_day_id", "version_number"),
        )
    version_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("journal_day_versions")}
    if "ix_journal_day_versions_journal_day_id" not in version_indexes:
        op.create_index("ix_journal_day_versions_journal_day_id", "journal_day_versions", ["journal_day_id"])
    if "ix_journal_day_versions_source" not in version_indexes:
        op.create_index("ix_journal_day_versions_source", "journal_day_versions", ["source"])
    if "ix_journal_day_versions_created_at" not in version_indexes:
        op.create_index("ix_journal_day_versions_created_at", "journal_day_versions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_journal_day_versions_created_at", table_name="journal_day_versions")
    op.drop_index("ix_journal_day_versions_source", table_name="journal_day_versions")
    op.drop_index("ix_journal_day_versions_journal_day_id", table_name="journal_day_versions")
    op.drop_table("journal_day_versions")
    op.drop_index("ix_journal_items_review_status", table_name="journal_items")
    op.drop_column("journal_items", "review_status")
    op.drop_index("ix_journal_items_canonical_key", table_name="journal_items")
    op.drop_column("journal_items", "canonical_key")
    op.drop_column("journal_days", "meaning_score")
    op.drop_column("journal_days", "energy_score")
    op.drop_column("journal_days", "mood_score")
    op.drop_column("journal_days", "model_consent")
