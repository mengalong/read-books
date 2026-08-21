"""增加考试快照版本

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-21 10:00:00.000000
"""

from typing import Sequence, Union
from uuid import uuid4
import json

from alembic import op
import sqlalchemy as sa


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_payload(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value or {}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("exam_attempts"):
        attempt_columns = {column["name"] for column in inspector.get_columns("exam_attempts")}
        with op.batch_alter_table("exam_attempts") as batch_op:
            if "snapshot_version" not in attempt_columns:
                batch_op.add_column(sa.Column("snapshot_version", sa.Integer(), nullable=True))
            if "quiz_snapshot" not in attempt_columns:
                batch_op.add_column(sa.Column("quiz_snapshot", sa.JSON(), nullable=True))
        attempt_indexes = {index["name"] for index in inspector.get_indexes("exam_attempts")}
        if "ix_exam_attempts_snapshot_version" not in attempt_indexes:
            op.create_index(
                "ix_exam_attempts_snapshot_version",
                "exam_attempts",
                ["snapshot_version"],
            )

    created_version_table = False
    if not inspector.has_table("exam_share_versions"):
        op.create_table(
            "exam_share_versions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("exam_share_id", sa.String(length=36), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("quiz_snapshot", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["exam_share_id"], ["exam_shares.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("exam_share_id", "version"),
        )
        op.create_index(
            "ix_exam_share_versions_exam_share_id",
            "exam_share_versions",
            ["exam_share_id"],
        )
        op.create_index(
            "ix_exam_share_versions_version",
            "exam_share_versions",
            ["version"],
        )
        created_version_table = True

    if not inspector.has_table("exam_shares"):
        return

    exam_shares = sa.table(
        "exam_shares",
        sa.column("id", sa.String(length=36)),
        sa.column("snapshot_version", sa.Integer()),
        sa.column("quiz_snapshot", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    exam_share_versions = sa.table(
        "exam_share_versions",
        sa.column("id", sa.String(length=36)),
        sa.column("exam_share_id", sa.String(length=36)),
        sa.column("version", sa.Integer()),
        sa.column("quiz_snapshot", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    if created_version_table:
        for row in bind.execute(sa.select(exam_shares)).mappings():
            bind.execute(
                exam_share_versions.insert().values(
                    id=str(uuid4()),
                    exam_share_id=row["id"],
                    version=row["snapshot_version"] or 1,
                    quiz_snapshot=_json_payload(row["quiz_snapshot"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

    if inspector.has_table("exam_attempts"):
        exam_attempts = sa.table(
            "exam_attempts",
            sa.column("id", sa.String(length=36)),
            sa.column("exam_share_id", sa.String(length=36)),
            sa.column("snapshot_version", sa.Integer()),
            sa.column("quiz_snapshot", sa.JSON()),
        )
        rows = bind.execute(
            sa.select(
                exam_attempts.c.id,
                exam_shares.c.snapshot_version,
                exam_shares.c.quiz_snapshot,
            ).select_from(
                exam_attempts.join(
                    exam_shares,
                    exam_attempts.c.exam_share_id == exam_shares.c.id,
                )
            )
        ).mappings()
        for row in rows:
            bind.execute(
                exam_attempts.update()
                .where(exam_attempts.c.id == row["id"])
                .values(
                    snapshot_version=row["snapshot_version"] or 1,
                    quiz_snapshot=_json_payload(row["quiz_snapshot"]),
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("exam_share_versions"):
        op.drop_index("ix_exam_share_versions_version", table_name="exam_share_versions")
        op.drop_index("ix_exam_share_versions_exam_share_id", table_name="exam_share_versions")
        op.drop_table("exam_share_versions")
    if inspector.has_table("exam_attempts"):
        attempt_columns = {column["name"] for column in inspector.get_columns("exam_attempts")}
        attempt_indexes = {index["name"] for index in inspector.get_indexes("exam_attempts")}
        if "ix_exam_attempts_snapshot_version" in attempt_indexes:
            op.drop_index("ix_exam_attempts_snapshot_version", table_name="exam_attempts")
        with op.batch_alter_table("exam_attempts") as batch_op:
            if "quiz_snapshot" in attempt_columns:
                batch_op.drop_column("quiz_snapshot")
            if "snapshot_version" in attempt_columns:
                batch_op.drop_column("snapshot_version")
