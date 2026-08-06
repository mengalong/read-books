"""统一试卷满分为100分

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-06 18:00:00.000000
"""

from collections.abc import Iterable
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None

TOTAL_SCORE = 100.0
TYPE_WEIGHTS = {
    "single": Decimal("6"),
    "multiple": Decimal("10"),
    "short": Decimal("20"),
}


def _allocate(weights: list[Decimal], total_score: float, decimal_places: int) -> list[float]:
    scale = 10**decimal_places
    total_units = int(
        (Decimal(str(total_score)) * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    total_weight = sum(weights)
    exact_units = [Decimal(total_units) * weight / total_weight for weight in weights]
    units = [int(value.to_integral_value(rounding=ROUND_FLOOR)) for value in exact_units]
    remaining = total_units - sum(units)
    priority = sorted(
        range(len(weights)),
        key=lambda index: (exact_units[index] - units[index], weights[index], -index),
        reverse=True,
    )
    for index in priority[:remaining]:
        units[index] += 1
    return [value / scale for value in units]


def _rubric_weights(rubric: list[dict[str, Any]]) -> list[Decimal]:
    weights = []
    for item in rubric:
        try:
            weight = Decimal(str(item.get("score", 0)))
        except (InvalidOperation, ValueError):
            weight = Decimal("0")
        weights.append(weight if weight > 0 else Decimal("1"))
    return weights


def _normalize_rubric(rubric: Any, max_score: float) -> list[dict[str, Any]]:
    if not isinstance(rubric, list) or not rubric:
        return []
    items = [item for item in rubric if isinstance(item, dict)]
    if not items:
        return []
    scores = _allocate(_rubric_weights(items), max_score, 2)
    return [
        {**item, "score": score}
        for item, score in zip(items, scores, strict=True)
    ]


def _scale_score(score: Any, old_max: Any, new_max: float) -> float:
    old_maximum = float(old_max or 0)
    if old_maximum <= 0:
        return 0.0
    return round(float(score or 0) / old_maximum * new_max, 2)


def _sum_scores(rows: Iterable[Any]) -> float:
    return round(sum(float(row.score or 0) for row in rows), 1)


def upgrade() -> None:
    bind = op.get_bind()
    quizzes = sa.table(
        "quizzes",
        sa.column("id", sa.String()),
        sa.column("total_score", sa.Float()),
        sa.column("max_score", sa.Float()),
    )
    questions = sa.table(
        "questions",
        sa.column("id", sa.String()),
        sa.column("quiz_id", sa.String()),
        sa.column("position", sa.Integer()),
        sa.column("question_type", sa.String()),
        sa.column("grading_rubric", sa.JSON()),
        sa.column("max_score", sa.Float()),
    )
    legacy_answers = sa.table(
        "answers",
        sa.column("id", sa.String()),
        sa.column("quiz_id", sa.String()),
        sa.column("question_id", sa.String()),
        sa.column("score", sa.Float()),
        sa.column("max_score", sa.Float()),
    )
    review_tasks = sa.table(
        "review_tasks",
        sa.column("id", sa.String()),
        sa.column("quiz_id", sa.String()),
        sa.column("total_score", sa.Float()),
        sa.column("max_score", sa.Float()),
    )
    review_answers = sa.table(
        "review_answers",
        sa.column("id", sa.String()),
        sa.column("review_task_id", sa.String()),
        sa.column("question_id", sa.String()),
        sa.column("score", sa.Float()),
        sa.column("max_score", sa.Float()),
    )
    exam_shares = sa.table(
        "exam_shares",
        sa.column("id", sa.String()),
        sa.column("quiz_snapshot", sa.JSON()),
        sa.column("max_score", sa.Float()),
    )
    exam_attempts = sa.table(
        "exam_attempts",
        sa.column("id", sa.String()),
        sa.column("exam_share_id", sa.String()),
        sa.column("total_score", sa.Float()),
        sa.column("max_score", sa.Float()),
    )
    exam_answers = sa.table(
        "exam_answers",
        sa.column("id", sa.String()),
        sa.column("exam_attempt_id", sa.String()),
        sa.column("snapshot_question_id", sa.String()),
        sa.column("score", sa.Float()),
        sa.column("max_score", sa.Float()),
    )

    for quiz in bind.execute(sa.select(quizzes)).mappings():
        question_rows = list(
            bind.execute(
                sa.select(questions)
                .where(questions.c.quiz_id == quiz.id)
                .order_by(questions.c.position, questions.c.id)
            ).mappings()
        )
        if not question_rows:
            continue
        scores = _allocate(
            [TYPE_WEIGHTS[row.question_type] for row in question_rows], TOTAL_SCORE, 1
        )
        score_map = {}
        for row, new_max in zip(question_rows, scores, strict=True):
            score_map[row.id] = (row.max_score, new_max)
            values = {"max_score": new_max}
            if row.question_type == "short":
                values["grading_rubric"] = _normalize_rubric(
                    row.grading_rubric, new_max
                )
            bind.execute(
                questions.update().where(questions.c.id == row.id).values(**values)
            )

        answer_rows = list(
            bind.execute(
                sa.select(legacy_answers).where(legacy_answers.c.quiz_id == quiz.id)
            ).mappings()
        )
        for answer in answer_rows:
            old_max, new_max = score_map[answer.question_id]
            bind.execute(
                legacy_answers.update()
                .where(legacy_answers.c.id == answer.id)
                .values(
                    score=_scale_score(answer.score, old_max, new_max),
                    max_score=new_max,
                )
            )
        quiz_values = {"max_score": TOTAL_SCORE}
        if quiz.total_score is not None:
            updated = bind.execute(
                sa.select(legacy_answers.c.score).where(
                    legacy_answers.c.quiz_id == quiz.id
                )
            ).all()
            quiz_values["total_score"] = _sum_scores(updated)
        bind.execute(quizzes.update().where(quizzes.c.id == quiz.id).values(**quiz_values))

        for review in bind.execute(
            sa.select(review_tasks).where(review_tasks.c.quiz_id == quiz.id)
        ).mappings():
            for answer in bind.execute(
                sa.select(review_answers).where(
                    review_answers.c.review_task_id == review.id
                )
            ).mappings():
                _, new_max = score_map[answer.question_id]
                bind.execute(
                    review_answers.update()
                    .where(review_answers.c.id == answer.id)
                    .values(
                        score=_scale_score(answer.score, answer.max_score, new_max),
                        max_score=new_max,
                    )
                )
            review_values = {"max_score": TOTAL_SCORE}
            if review.total_score is not None:
                updated = bind.execute(
                    sa.select(review_answers.c.score).where(
                        review_answers.c.review_task_id == review.id
                    )
                ).all()
                review_values["total_score"] = _sum_scores(updated)
            bind.execute(
                review_tasks.update()
                .where(review_tasks.c.id == review.id)
                .values(**review_values)
            )

    for share in bind.execute(sa.select(exam_shares)).mappings():
        snapshot = dict(share.quiz_snapshot or {})
        snapshot_questions = [
            dict(item)
            for item in snapshot.get("questions", [])
            if isinstance(item, dict) and item.get("question_type") in TYPE_WEIGHTS
        ]
        if not snapshot_questions:
            continue
        scores = _allocate(
            [TYPE_WEIGHTS[item["question_type"]] for item in snapshot_questions],
            TOTAL_SCORE,
            1,
        )
        score_map = {}
        for item, new_max in zip(snapshot_questions, scores, strict=True):
            question_id = str(item.get("id", ""))
            score_map[question_id] = (item.get("max_score"), new_max)
            item["max_score"] = new_max
            if item["question_type"] == "short":
                item["grading_rubric"] = _normalize_rubric(
                    item.get("grading_rubric"), new_max
                )
        snapshot["max_score"] = TOTAL_SCORE
        snapshot["questions"] = snapshot_questions
        bind.execute(
            exam_shares.update()
            .where(exam_shares.c.id == share.id)
            .values(quiz_snapshot=snapshot, max_score=TOTAL_SCORE)
        )

        for attempt in bind.execute(
            sa.select(exam_attempts).where(exam_attempts.c.exam_share_id == share.id)
        ).mappings():
            for answer in bind.execute(
                sa.select(exam_answers).where(
                    exam_answers.c.exam_attempt_id == attempt.id
                )
            ).mappings():
                old_max, new_max = score_map[answer.snapshot_question_id]
                bind.execute(
                    exam_answers.update()
                    .where(exam_answers.c.id == answer.id)
                    .values(
                        score=_scale_score(answer.score, old_max, new_max),
                        max_score=new_max,
                    )
                )
            attempt_values = {"max_score": TOTAL_SCORE}
            if attempt.total_score is not None:
                updated = bind.execute(
                    sa.select(exam_answers.c.score).where(
                        exam_answers.c.exam_attempt_id == attempt.id
                    )
                ).all()
                attempt_values["total_score"] = _sum_scores(updated)
            bind.execute(
                exam_attempts.update()
                .where(exam_attempts.c.id == attempt.id)
                .values(**attempt_values)
            )


def downgrade() -> None:
    pass
