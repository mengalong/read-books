"""回填历史题目事实签名

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-03 21:30:00.000000
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

from app.services.question_dedup import build_question_signature


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if context.is_offline_mode():
        return

    questions = sa.table(
        "questions",
        sa.column("id", sa.String(length=36)),
        sa.column("question_subtype", sa.String(length=40)),
        sa.column("prompt", sa.Text()),
        sa.column("options", sa.JSON()),
        sa.column("correct_answers", sa.JSON()),
        sa.column("knowledge_point", sa.String(length=120)),
        sa.column("reference_answer", sa.Text()),
        sa.column("fact_key", sa.String(length=1000)),
        sa.column("fact_claim", sa.Text()),
        sa.column("semantic_signature", sa.JSON()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(questions).where(
            sa.or_(
                questions.c.fact_key.is_(None),
                questions.c.fact_claim.is_(None),
                questions.c.semantic_signature.is_(None),
            )
        )
    ).mappings()
    for row in rows:
        signature = build_question_signature(row)
        connection.execute(
            questions.update()
            .where(questions.c.id == row["id"])
            .values(
                fact_key=signature["fact_key"],
                fact_claim=signature["fact_claim"],
                semantic_signature=signature,
            )
        )


def downgrade() -> None:
    # 回填数据仍兼容上一版本的可空字段，降级时不清空后来生成的签名。
    pass
