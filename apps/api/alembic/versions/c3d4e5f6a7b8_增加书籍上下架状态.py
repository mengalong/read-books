"""增加书籍上下架状态

Revision ID: c3d4e5f6a7b8
Revises: b9c1d2e3f4a5
Create Date: 2026-08-04 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b9c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("books")}
    if "shelf_status" not in columns:
        op.add_column(
            "books",
            sa.Column(
                "shelf_status",
                sa.String(length=20),
                nullable=False,
                server_default="active",
            ),
        )
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("books")}
    if "ix_books_shelf_status" not in indexes:
        op.create_index("ix_books_shelf_status", "books", ["shelf_status"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("books")}
    if "ix_books_shelf_status" in indexes:
        op.drop_index("ix_books_shelf_status", table_name="books")
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("books")}
    if "shelf_status" in columns:
        op.drop_column("books", "shelf_status")
