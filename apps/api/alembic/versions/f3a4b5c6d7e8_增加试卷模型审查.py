"""增加试卷模型审查

Revision ID: f3a4b5c6d7e8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-05 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("quizzes")}
    additions = [
        ("quality_review_status", sa.String(length=20), "not_started"),
        ("quality_review_task_id", sa.String(length=36), None),
        ("quality_review_result", sa.JSON(), None),
        ("quality_review_error", sa.Text(), None),
        ("quality_review_requested_at", sa.DateTime(timezone=True), None),
        ("quality_review_completed_at", sa.DateTime(timezone=True), None),
    ]
    with op.batch_alter_table("quizzes") as batch_op:
        for name, column_type, default in additions:
            if name not in columns:
                kwargs = {"nullable": True}
                if default is not None:
                    kwargs["server_default"] = default
                batch_op.add_column(sa.Column(name, column_type, **kwargs))
        if "quality_review_status" not in columns:
            batch_op.alter_column("quality_review_status", server_default=None)
        for name in ("quality_review_status", "quality_review_task_id"):
            index_name = f"ix_quizzes_{name}"
            existing_indexes = {
                index["name"] for index in inspector.get_indexes("quizzes")
            }
            if index_name not in existing_indexes:
                batch_op.create_index(index_name, [name])


def downgrade() -> None:
    with op.batch_alter_table("quizzes") as batch_op:
        for name in ("quality_review_status", "quality_review_task_id"):
            batch_op.drop_index(f"ix_quizzes_{name}")
        for name in (
            "quality_review_completed_at",
            "quality_review_requested_at",
            "quality_review_error",
            "quality_review_result",
            "quality_review_task_id",
            "quality_review_status",
        ):
            batch_op.drop_column(name)
