"""增加书籍预出题状态

Revision ID: a42e9d7c1b50
Revises: 91bd3c6e7a42
Create Date: 2026-08-02 21:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a42e9d7c1b50"
down_revision: Union[str, Sequence[str], None] = "91bd3c6e7a42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BOOK_COLUMNS = (
    ("pre_generation_enabled", sa.Boolean(), False),
    ("pre_generation_status", sa.String(length=20), "disabled"),
    ("pre_generation_error", sa.Text(), None),
    ("pre_generation_quiz_id", sa.String(length=36), None),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("books")}
    for name, column_type, default in BOOK_COLUMNS:
        if name in existing_columns:
            continue
        kwargs = {"nullable": default is None}
        if default is not None:
            kwargs["server_default"] = sa.text("0") if default is False else default
        op.add_column("books", sa.Column(name, column_type, **kwargs))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("books")}
    for name, _, _ in reversed(BOOK_COLUMNS):
        if name in existing_columns:
            op.drop_column("books", name)
