"""记录模型测试状态

Revision ID: 7c2b8e4a1f6d
Revises: 4e2a7f1d9c3b
Create Date: 2026-08-02 18:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c2b8e4a1f6d"
down_revision: Union[str, Sequence[str], None] = "4e2a7f1d9c3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_COLUMNS = (
    ("last_test_status", sa.String(length=20)),
    ("last_test_message", sa.Text()),
    ("last_tested_at", sa.DateTime(timezone=True)),
    ("last_test_latency_ms", sa.Integer()),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("model_configurations")}
    for name, column_type in NEW_COLUMNS:
        if name not in existing_columns:
            op.add_column("model_configurations", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("model_configurations")}
    for name, _ in reversed(NEW_COLUMNS):
        if name in existing_columns:
            op.drop_column("model_configurations", name)
