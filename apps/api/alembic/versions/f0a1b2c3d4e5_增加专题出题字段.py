"""增加专题出题字段

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-09-03 17:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("quizzes") as batch_op:
        batch_op.add_column(
            sa.Column(
                "generation_theme",
                sa.String(length=30),
                nullable=False,
                server_default="general",
            )
        )
        batch_op.add_column(
            sa.Column("theme_config", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.create_index("ix_quizzes_generation_theme", ["generation_theme"])

    with op.batch_alter_table("quiz_generation_tasks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "generation_theme",
                sa.String(length=30),
                nullable=False,
                server_default="general",
            )
        )
        batch_op.add_column(
            sa.Column("theme_config", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.create_index(
            "ix_quiz_generation_tasks_generation_theme", ["generation_theme"]
        )

    with op.batch_alter_table("questions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "question_subtype",
                sa.String(length=40),
                nullable=False,
                server_default="general",
            )
        )
        batch_op.add_column(
            sa.Column("quote_entry_ids", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column("source_segment_ids", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.create_index("ix_questions_question_subtype", ["question_subtype"])


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_index("ix_questions_question_subtype")
        batch_op.drop_column("source_segment_ids")
        batch_op.drop_column("quote_entry_ids")
        batch_op.drop_column("question_subtype")
    with op.batch_alter_table("quiz_generation_tasks") as batch_op:
        batch_op.drop_index("ix_quiz_generation_tasks_generation_theme")
        batch_op.drop_column("theme_config")
        batch_op.drop_column("generation_theme")
    with op.batch_alter_table("quizzes") as batch_op:
        batch_op.drop_index("ix_quizzes_generation_theme")
        batch_op.drop_column("theme_config")
        batch_op.drop_column("generation_theme")
