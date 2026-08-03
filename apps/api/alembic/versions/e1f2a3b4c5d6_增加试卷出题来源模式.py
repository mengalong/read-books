"""增加试卷出题来源模式

Revision ID: e1f2a3b4c5d6
Revises: d7e8f9a0b1c2
Create Date: 2026-08-03 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in ("quizzes", "quiz_generation_tasks"):
        inspector = sa.inspect(op.get_bind())
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "source_mode" not in existing_columns:
            op.add_column(
                table_name,
                sa.Column(
                    "source_mode",
                    sa.String(length=30),
                    nullable=False,
                    server_default="pdf",
                ),
            )


def downgrade() -> None:
    for table_name in ("quiz_generation_tasks", "quizzes"):
        inspector = sa.inspect(op.get_bind())
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "source_mode" in existing_columns:
            op.drop_column(table_name, "source_mode")
