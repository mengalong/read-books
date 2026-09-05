"""增加题库和试卷引用

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-09-06 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "question_bank_entries" not in tables:
        op.create_table(
            "question_bank_entries",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("book_id", sa.String(length=36), nullable=False),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("origin_quiz_id", sa.String(length=36), nullable=True),
            sa.Column("origin_question_id", sa.String(length=36), nullable=True),
            sa.Column("question_type", sa.String(length=20), nullable=False),
            sa.Column("question_subtype", sa.String(length=40), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("options", sa.JSON(), nullable=True),
            sa.Column("correct_answers", sa.JSON(), nullable=True),
            sa.Column("explanation", sa.Text(), nullable=False),
            sa.Column("knowledge_point", sa.String(length=120), nullable=False),
            sa.Column("difficulty", sa.String(length=20), nullable=False),
            sa.Column("estimated_seconds", sa.Integer(), nullable=False),
            sa.Column("reference_answer", sa.Text(), nullable=True),
            sa.Column("grading_rubric", sa.JSON(), nullable=True),
            sa.Column("source_chunk_ids", sa.JSON(), nullable=True),
            sa.Column("quote_entry_ids", sa.JSON(), nullable=True),
            sa.Column("plot_event_ids", sa.JSON(), nullable=True),
            sa.Column("source_segment_ids", sa.JSON(), nullable=True),
            sa.Column("fact_key", sa.String(length=1000), nullable=True),
            sa.Column("fact_claim", sa.Text(), nullable=True),
            sa.Column("semantic_signature", sa.JSON(), nullable=True),
            sa.Column("source_evidence", sa.JSON(), nullable=True),
            sa.Column("source_mode", sa.String(length=30), nullable=True),
            sa.Column("max_score", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("use_count", sa.Integer(), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        for name, columns in (
            ("book_id", ["book_id"]),
            ("created_by_user_id", ["created_by_user_id"]),
            ("origin_quiz_id", ["origin_quiz_id"]),
            ("origin_question_id", ["origin_question_id"]),
            ("question_type", ["question_type"]),
            ("question_subtype", ["question_subtype"]),
            ("fact_key", ["fact_key"]),
            ("status", ["status"]),
            ("use_count", ["use_count"]),
        ):
            op.create_index(f"ix_question_bank_entries_{name}", "question_bank_entries", columns)

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "question_bank_usages" not in tables:
        op.create_table(
            "question_bank_usages",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("book_id", sa.String(length=36), nullable=False),
            sa.Column("entry_id", sa.String(length=36), nullable=False),
            sa.Column("quiz_id", sa.String(length=36), nullable=True),
            sa.Column("question_id", sa.String(length=36), nullable=True),
            sa.Column("quiz_title_snapshot", sa.String(length=200), nullable=False),
            sa.Column("question_position", sa.Integer(), nullable=True),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["entry_id"], ["question_bank_entries.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("entry_id", "quiz_id"),
        )
        for name, columns in (
            ("book_id", ["book_id"]),
            ("entry_id", ["entry_id"]),
            ("quiz_id", ["quiz_id"]),
            ("question_id", ["question_id"]),
            ("used_at", ["used_at"]),
        ):
            op.create_index(f"ix_question_bank_usages_{name}", "question_bank_usages", columns)

    question_columns = {column["name"] for column in inspector.get_columns("questions")}
    if "question_bank_entry_id" not in question_columns:
        with op.batch_alter_table("questions") as batch_op:
            batch_op.add_column(
                sa.Column("question_bank_entry_id", sa.String(length=36), nullable=True)
            )
            batch_op.create_index("ix_questions_question_bank_entry_id", ["question_bank_entry_id"])
            batch_op.create_foreign_key(
                "fk_questions_question_bank_entry_id",
                "question_bank_entries",
                ["question_bank_entry_id"],
                ["id"],
                ondelete="SET NULL",
            )

    inspector = sa.inspect(bind)
    task_columns = {
        column["name"] for column in inspector.get_columns("quiz_generation_tasks")
    }
    if "use_question_bank" not in task_columns:
        with op.batch_alter_table("quiz_generation_tasks") as batch_op:
            batch_op.add_column(
                sa.Column("use_question_bank", sa.Boolean(), nullable=True, server_default=sa.true())
            )
            batch_op.alter_column("use_question_bank", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_constraint("fk_questions_question_bank_entry_id", type_="foreignkey")
        batch_op.drop_index("ix_questions_question_bank_entry_id")
        batch_op.drop_column("question_bank_entry_id")
    for name in (
        "used_at",
        "question_id",
        "quiz_id",
        "entry_id",
        "book_id",
    ):
        op.drop_index(f"ix_question_bank_usages_{name}", table_name="question_bank_usages")
    op.drop_table("question_bank_usages")
    for name in (
        "use_count",
        "status",
        "fact_key",
        "question_subtype",
        "question_type",
        "origin_question_id",
        "origin_quiz_id",
        "created_by_user_id",
        "book_id",
    ):
        op.drop_index(f"ix_question_bank_entries_{name}", table_name="question_bank_entries")
    op.drop_table("question_bank_entries")
    with op.batch_alter_table("quiz_generation_tasks") as batch_op:
        batch_op.drop_column("use_question_bank")
