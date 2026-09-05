"""保存剧情梗概结构化内容

Revision ID: f5a6b7c8d9e0
Revises: f4a5b6c7d8e9
Create Date: 2026-09-05 19:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "structured_content" not in {
        column["name"] for column in inspector.get_columns("resource_materials")
    }:
        with op.batch_alter_table("resource_materials") as batch_op:
            batch_op.add_column(
                sa.Column("structured_content", sa.JSON(), nullable=True)
            )


def downgrade() -> None:
    with op.batch_alter_table("resource_materials") as batch_op:
        batch_op.drop_column("structured_content")
