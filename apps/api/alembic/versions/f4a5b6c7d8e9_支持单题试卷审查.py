"""支持单题试卷审查

Revision ID: f4a5b6c7d8e9
Revises: f3a4b5c6d7e8
Create Date: 2026-09-05 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("quizzes")}
    indexes = {index["name"] for index in inspector.get_indexes("quizzes")}
    with op.batch_alter_table("quizzes") as batch_op:
        if "quality_review_question_id" not in columns:
            batch_op.add_column(
                sa.Column("quality_review_question_id", sa.String(length=36), nullable=True)
            )
        if "ix_quizzes_quality_review_question_id" not in indexes:
            batch_op.create_index(
                "ix_quizzes_quality_review_question_id", ["quality_review_question_id"]
            )


def downgrade() -> None:
    with op.batch_alter_table("quizzes") as batch_op:
        batch_op.drop_index("ix_quizzes_quality_review_question_id")
        batch_op.drop_column("quality_review_question_id")
