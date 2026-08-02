"""增加异步出题和复习任务

Revision ID: d7e8f9a0b1c2
Revises: c6e7a8b9d0f1
Create Date: 2026-08-03 10:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "c6e7a8b9d0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "quizzes" in tables:
        quiz_columns = {column["name"] for column in inspector.get_columns("quizzes")}
        if "generation_task_id" not in quiz_columns:
            op.add_column("quizzes", sa.Column("generation_task_id", sa.String(length=36), nullable=True))
            op.create_index("ix_quizzes_generation_task_id", "quizzes", ["generation_task_id"])
    if "quiz_generation_tasks" not in tables:
        op.create_table(
            "quiz_generation_tasks",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("book_id", sa.String(length=36), nullable=False),
            sa.Column("task_type", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("total_questions", sa.Integer(), nullable=False),
            sa.Column("completed_questions", sa.Integer(), nullable=False),
            sa.Column("current_question_position", sa.Integer(), nullable=True),
            sa.Column("current_phase", sa.String(length=120), nullable=False),
            sa.Column("difficulty", sa.String(length=20), nullable=False),
            sa.Column("duration_minutes", sa.Integer(), nullable=False),
            sa.Column("single_count", sa.Integer(), nullable=False),
            sa.Column("multiple_count", sa.Integer(), nullable=False),
            sa.Column("short_count", sa.Integer(), nullable=False),
            sa.Column("page_start", sa.Integer(), nullable=True),
            sa.Column("page_end", sa.Integer(), nullable=True),
            sa.Column("quiz_id", sa.String(length=36), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("book_id", "status", "quiz_id"):
            op.create_index(f"ix_quiz_generation_tasks_{column}", "quiz_generation_tasks", [column])

    if "review_tasks" not in tables:
        op.create_table(
            "review_tasks",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("book_id", sa.String(length=36), nullable=False),
            sa.Column("quiz_id", sa.String(length=36), nullable=False),
            sa.Column("attempt_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("total_score", sa.Float(), nullable=True),
            sa.Column("max_score", sa.Float(), nullable=False),
            sa.Column("elapsed_seconds", sa.Integer(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_review_date", sa.Date(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("book_id", "quiz_id", "status"):
            op.create_index(f"ix_review_tasks_{column}", "review_tasks", [column])

    if "review_answers" not in tables:
        op.create_table(
            "review_answers",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("review_task_id", sa.String(length=36), nullable=False),
            sa.Column("question_id", sa.String(length=36), nullable=False),
            sa.Column("selected_answers", sa.JSON(), nullable=False),
            sa.Column("text_answer", sa.Text(), nullable=True),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column("max_score", sa.Float(), nullable=False),
            sa.Column("is_correct", sa.Boolean(), nullable=False),
            sa.Column("feedback", sa.Text(), nullable=False),
            sa.Column("matched_points", sa.JSON(), nullable=False),
            sa.Column("missing_points", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["review_task_id"], ["review_tasks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("review_task_id", "question_id"),
        )
        op.create_index("ix_review_answers_review_task_id", "review_answers", ["review_task_id"])
        op.create_index("ix_review_answers_question_id", "review_answers", ["question_id"])

    bind = op.get_bind()
    bind.execute(sa.text("""
        INSERT INTO review_tasks (
            id, book_id, quiz_id, attempt_number, status, total_score, max_score,
            elapsed_seconds, submitted_at, next_review_date, created_at, updated_at
        )
        SELECT q.id, q.book_id, q.id, 1, 'submitted', q.total_score, q.max_score,
               q.elapsed_seconds, q.submitted_at, q.next_review_date, q.created_at, q.updated_at
        FROM quizzes q
        WHERE q.status = 'submitted'
          AND NOT EXISTS (SELECT 1 FROM review_tasks r WHERE r.id = q.id)
    """))
    bind.execute(sa.text("""
        INSERT INTO review_answers (
            id, review_task_id, question_id, selected_answers, text_answer, score,
            max_score, is_correct, feedback, matched_points, missing_points, created_at, updated_at
        )
        SELECT a.id, a.quiz_id, a.question_id, a.selected_answers, a.text_answer, a.score,
               a.max_score, a.is_correct, a.feedback, a.matched_points, a.missing_points,
               a.created_at, a.updated_at
        FROM answers a
        WHERE EXISTS (SELECT 1 FROM review_tasks r WHERE r.id = a.quiz_id)
          AND NOT EXISTS (SELECT 1 FROM review_answers r WHERE r.id = a.id)
    """))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "quizzes" in inspector.get_table_names():
        quiz_columns = {column["name"] for column in inspector.get_columns("quizzes")}
        if "generation_task_id" in quiz_columns:
            op.drop_index("ix_quizzes_generation_task_id", table_name="quizzes")
            op.drop_column("quizzes", "generation_task_id")
    for table in ("review_answers", "review_tasks", "quiz_generation_tasks"):
        if table in inspector.get_table_names():
            op.drop_table(table)
