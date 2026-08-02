"""增加提示词模板管理

Revision ID: 91bd3c6e7a42
Revises: 7c2b8e4a1f6d
Create Date: 2026-08-02 20:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "91bd3c6e7a42"
down_revision: Union[str, Sequence[str], None] = "7c2b8e4a1f6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("prompt_templates"):
        return
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("prompt_type", sa.String(length=30), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("user_prompt", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_templates_prompt_type", "prompt_templates", ["prompt_type"])
    op.create_index("ix_prompt_templates_is_active", "prompt_templates", ["is_active"])


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("prompt_templates"):
        op.drop_index("ix_prompt_templates_is_active", table_name="prompt_templates")
        op.drop_index("ix_prompt_templates_prompt_type", table_name="prompt_templates")
        op.drop_table("prompt_templates")
