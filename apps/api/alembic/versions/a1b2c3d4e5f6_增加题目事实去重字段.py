"""增加题目事实去重字段

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-09-03 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.add_column(sa.Column("fact_key", sa.String(length=1000), nullable=True))
        batch_op.add_column(sa.Column("fact_claim", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("semantic_signature", sa.JSON(), nullable=True))
        batch_op.create_index("ix_questions_fact_key", ["fact_key"])


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_index("ix_questions_fact_key")
        batch_op.drop_column("semantic_signature")
        batch_op.drop_column("fact_claim")
        batch_op.drop_column("fact_key")
