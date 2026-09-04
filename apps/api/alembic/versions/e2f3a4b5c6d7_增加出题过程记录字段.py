"""增加出题过程记录字段

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-09-04 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("quiz_generation_tasks") as batch_op:
        batch_op.add_column(sa.Column("question_states", sa.JSON(), nullable=True))

    with op.batch_alter_table("model_usage_records") as batch_op:
        batch_op.add_column(sa.Column("question_position", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("request_messages", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("model_response", sa.Text(), nullable=True))

    op.create_index(
        "ix_model_usage_records_question_position",
        "model_usage_records",
        ["question_position"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_usage_records_question_position", table_name="model_usage_records"
    )
    with op.batch_alter_table("model_usage_records") as batch_op:
        batch_op.drop_column("model_response")
        batch_op.drop_column("request_messages")
        batch_op.drop_column("question_position")

    with op.batch_alter_table("quiz_generation_tasks") as batch_op:
        batch_op.drop_column("question_states")
