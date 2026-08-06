"""增加考试分享与匿名答题

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-06 16:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("exam_shares"):
        op.create_table(
            "exam_shares",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("share_code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("quiz_id", sa.String(length=36), nullable=True),
            sa.Column("book_id", sa.String(length=36), nullable=True),
            sa.Column("owner_user_id", sa.String(length=36), nullable=False),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("quiz_snapshot", sa.JSON(), nullable=False),
            sa.Column("snapshot_version", sa.Integer(), nullable=False),
            sa.Column("book_title", sa.String(length=200), nullable=False),
            sa.Column("book_author", sa.String(length=120), nullable=False),
            sa.Column("quiz_title", sa.String(length=200), nullable=False),
            sa.Column("source_mode", sa.String(length=30), nullable=False),
            sa.Column("difficulty", sa.String(length=20), nullable=False),
            sa.Column("duration_minutes", sa.Integer(), nullable=False),
            sa.Column("max_score", sa.Float(), nullable=False),
            sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("share_code"),
        )
        for column in (
            "share_code", "quiz_id", "book_id", "owner_user_id", "workspace_id",
            "status", "source_mode", "expires_at", "last_attempt_at",
        ):
            op.create_index(f"ix_exam_shares_{column}", "exam_shares", [column])

    if not inspector.has_table("exam_attempts"):
        op.create_table(
            "exam_attempts",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("exam_share_id", sa.String(length=36), nullable=False),
            sa.Column("participant_type", sa.String(length=20), nullable=False),
            sa.Column("participant_user_id", sa.String(length=36), nullable=True),
            sa.Column("participant_name", sa.String(length=120), nullable=False),
            sa.Column("access_token_hash", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("total_score", sa.Float(), nullable=True),
            sa.Column("max_score", sa.Float(), nullable=False),
            sa.Column("elapsed_seconds", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("grading_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["exam_share_id"], ["exam_shares.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["participant_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("access_token_hash"),
            sa.UniqueConstraint("exam_share_id", "participant_user_id"),
        )
        for column in (
            "exam_share_id", "participant_type", "participant_user_id", "access_token_hash",
            "status", "submitted_at", "completed_at",
        ):
            op.create_index(f"ix_exam_attempts_{column}", "exam_attempts", [column])

    if not inspector.has_table("exam_answers"):
        op.create_table(
            "exam_answers",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("exam_attempt_id", sa.String(length=36), nullable=False),
            sa.Column("snapshot_question_id", sa.String(length=36), nullable=False),
            sa.Column("selected_answers", sa.JSON(), nullable=False),
            sa.Column("text_answer", sa.Text(), nullable=True),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column("max_score", sa.Float(), nullable=False),
            sa.Column("is_correct", sa.Boolean(), nullable=False),
            sa.Column("feedback", sa.Text(), nullable=False),
            sa.Column("matched_points", sa.JSON(), nullable=False),
            sa.Column("missing_points", sa.JSON(), nullable=False),
            sa.Column("grading_status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["exam_attempt_id"], ["exam_attempts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("exam_attempt_id", "snapshot_question_id"),
        )
        for column in ("exam_attempt_id", "snapshot_question_id", "grading_status"):
            op.create_index(f"ix_exam_answers_{column}", "exam_answers", [column])

    usage_columns = {column["name"] for column in inspector.get_columns("model_usage_records")}
    if "exam_share_id" not in usage_columns:
        op.add_column("model_usage_records", sa.Column("exam_share_id", sa.String(length=36)))
        op.create_index("ix_model_usage_records_exam_share_id", "model_usage_records", ["exam_share_id"])
    if "exam_attempt_id" not in usage_columns:
        op.add_column("model_usage_records", sa.Column("exam_attempt_id", sa.String(length=36)))
        op.create_index("ix_model_usage_records_exam_attempt_id", "model_usage_records", ["exam_attempt_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    usage_columns = {column["name"] for column in inspector.get_columns("model_usage_records")}
    if "exam_attempt_id" in usage_columns:
        op.drop_index("ix_model_usage_records_exam_attempt_id", table_name="model_usage_records")
        op.drop_column("model_usage_records", "exam_attempt_id")
    if "exam_share_id" in usage_columns:
        op.drop_index("ix_model_usage_records_exam_share_id", table_name="model_usage_records")
        op.drop_column("model_usage_records", "exam_share_id")
    for table in ("exam_answers", "exam_attempts", "exam_shares"):
        if sa.inspect(op.get_bind()).has_table(table):
            op.drop_table(table)
