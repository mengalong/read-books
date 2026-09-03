"""增加可信资料和台词表

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-09-03 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_materials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("book_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("material_type", sa.String(length=30), nullable=False),
        sa.Column("file_format", sa.String(length=20), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=True),
        sa.Column("episode_label", sa.String(length=80), nullable=True),
        sa.Column("version_label", sa.String(length=120), nullable=True),
        sa.Column("parse_status", sa.String(length=30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("segment_count", sa.Integer(), nullable=False),
        sa.Column("quote_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", "file_hash", name="uq_resource_material_book_hash"),
    )
    for column in ("book_id", "created_by_user_id", "material_type", "file_format", "file_hash", "parse_status"):
        op.create_index(f"ix_resource_materials_{column}", "resource_materials", [column])

    op.create_table(
        "material_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("book_id", sa.String(length=36), nullable=False),
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("season_number", sa.Integer(), nullable=True),
        sa.Column("episode_number", sa.Integer(), nullable=True),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("scene_label", sa.String(length=200), nullable=True),
        sa.Column("speaker", sa.String(length=120), nullable=True),
        sa.Column("speaker_origin", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["resource_materials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    segment_indexes = (
        "book_id",
        "material_id",
        "content_hash",
        "page_number",
        "season_number",
        "episode_number",
        "speaker",
        "speaker_origin",
    )
    for column in segment_indexes:
        op.create_index(f"ix_material_segments_{column}", "material_segments", [column])

    op.create_table(
        "quote_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("book_id", sa.String(length=36), nullable=False),
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("source_segment_ids", sa.JSON(), nullable=False),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("speaker", sa.String(length=120), nullable=True),
        sa.Column("speaker_origin", sa.String(length=20), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("season_number", sa.Integer(), nullable=True),
        sa.Column("episode_number", sa.Integer(), nullable=True),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("enabled_for_generation", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["resource_materials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "book_id",
        "material_id",
        "content_hash",
        "speaker",
        "speaker_origin",
        "season_number",
        "episode_number",
        "page_number",
        "review_status",
        "enabled_for_generation",
    ):
        op.create_index(f"ix_quote_entries_{column}", "quote_entries", [column])


def downgrade() -> None:
    op.drop_table("quote_entries")
    op.drop_table("material_segments")
    op.drop_table("resource_materials")
