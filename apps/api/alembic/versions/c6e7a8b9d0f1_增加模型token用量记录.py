"""增加模型 Token 用量记录

Revision ID: c6e7a8b9d0f1
Revises: a42e9d7c1b50
Create Date: 2026-08-02 22:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6e7a8b9d0f1"
down_revision: Union[str, Sequence[str], None] = "a42e9d7c1b50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "model_usage_records" in inspector.get_table_names():
        return
    op.create_table(
        "model_usage_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("task_type", sa.String(length=40), nullable=False),
        sa.Column("task_label", sa.String(length=240), nullable=False),
        sa.Column("phase", sa.String(length=50), nullable=False),
        sa.Column("call_number", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.String(length=36), nullable=True),
        sa.Column("quiz_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("task_id", "task_type", "phase", "status", "book_id", "quiz_id", "created_at"):
        op.create_index(f"ix_model_usage_records_{column}", "model_usage_records", [column])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "model_usage_records" in inspector.get_table_names():
        op.drop_table("model_usage_records")
