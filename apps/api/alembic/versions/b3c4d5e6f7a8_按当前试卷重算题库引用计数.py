"""按当前有效试卷重算题库引用计数

Revision ID: b3c4d5e6f7a8
Revises: a6b7c8d9e0f1
Create Date: 2026-09-07 11:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if not {"question_bank_entries", "question_bank_usages", "quizzes"}.issubset(tables):
        return

    # Old versions detached usages from deleted quizzes. They are not current
    # references and must not continue contributing to use_count.
    bind.execute(
        sa.text(
            """
            DELETE FROM question_bank_usages
            WHERE quiz_id IS NULL
               OR NOT EXISTS (
                   SELECT 1 FROM quizzes
                   WHERE quizzes.id = question_bank_usages.quiz_id
               )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE question_bank_entries
            SET use_count = (
                    SELECT COUNT(*)
                    FROM question_bank_usages
                    WHERE question_bank_usages.entry_id = question_bank_entries.id
                      AND question_bank_usages.quiz_id IS NOT NULL
                ),
                last_used_at = (
                    SELECT MAX(used_at)
                    FROM question_bank_usages
                    WHERE question_bank_usages.entry_id = question_bank_entries.id
                      AND question_bank_usages.quiz_id IS NOT NULL
                )
            """
        )
    )


def downgrade() -> None:
    # Removing detached historical usages is intentionally irreversible.
    pass
