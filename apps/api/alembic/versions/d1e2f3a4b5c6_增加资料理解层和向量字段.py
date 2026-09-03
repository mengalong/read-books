"""增加资料理解层和向量字段

Revision ID: d1e2f3a4b5c6
Revises: c3e4f5a6b7c8
Create Date: 2026-09-04 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("content_chunks") as batch_op:
        batch_op.add_column(sa.Column("embedding", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("embedding_model", sa.String(length=120), nullable=True))

    with op.batch_alter_table("material_segments") as batch_op:
        batch_op.add_column(sa.Column("embedding", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("embedding_model", sa.String(length=120), nullable=True))

    with op.batch_alter_table("quote_entries") as batch_op:
        batch_op.add_column(sa.Column("embedding", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("embedding_model", sa.String(length=120), nullable=True))

    op.create_table(
        "material_understandings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("book_id", sa.String(length=36), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_ref", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("key_entities", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_segment_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source_chunk_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("content_signature", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "book_id", "scope_type", "scope_ref", name="uq_material_understanding_scope"
        ),
    )
    op.create_index(
        "ix_material_understandings_book_id", "material_understandings", ["book_id"]
    )
    op.create_index(
        "ix_material_understandings_scope_type", "material_understandings", ["scope_type"]
    )
    op.create_index(
        "ix_material_understandings_scope_ref", "material_understandings", ["scope_ref"]
    )
    op.create_index(
        "ix_material_understandings_content_signature",
        "material_understandings",
        ["content_signature"],
    )
    op.create_index(
        "ix_material_understandings_status", "material_understandings", ["status"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_material_understandings_status", table_name="material_understandings"
    )
    op.drop_index(
        "ix_material_understandings_content_signature", table_name="material_understandings"
    )
    op.drop_index(
        "ix_material_understandings_scope_ref", table_name="material_understandings"
    )
    op.drop_index(
        "ix_material_understandings_scope_type", table_name="material_understandings"
    )
    op.drop_index(
        "ix_material_understandings_book_id", table_name="material_understandings"
    )
    op.drop_table("material_understandings")

    with op.batch_alter_table("quote_entries") as batch_op:
        batch_op.drop_column("embedding_model")
        batch_op.drop_column("embedding")

    with op.batch_alter_table("material_segments") as batch_op:
        batch_op.drop_column("embedding_model")
        batch_op.drop_column("embedding")

    with op.batch_alter_table("content_chunks") as batch_op:
        batch_op.drop_column("embedding_model")
        batch_op.drop_column("embedding")
