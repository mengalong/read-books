"""增加日记写作风格

Revision ID: c9d0e1f2a3b4
Revises: c8d9e0f1a2b3
Create Date: 2026-09-07 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("journal_days")}
    if "writing_style" not in columns:
        op.add_column(
            "journal_days",
            sa.Column(
                "writing_style",
                sa.String(length=30),
                nullable=False,
                server_default="natural",
            ),
        )


def downgrade() -> None:
    op.drop_column("journal_days", "writing_style")
