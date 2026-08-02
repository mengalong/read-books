"""增加模型配置表

Revision ID: 4e2a7f1d9c3b
Revises: f8d55e2d8b55
Create Date: 2026-08-02 17:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4e2a7f1d9c3b"
down_revision: Union[str, Sequence[str], None] = "f8d55e2d8b55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("model_configurations"):
        return
    op.create_table(
        "model_configurations",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("provider_mode", sa.String(length=30), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("timeout_ms", sa.Integer(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("model_configurations"):
        op.drop_table("model_configurations")
