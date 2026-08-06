"""记录考试终端与IP

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-06 21:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exam_attempts", sa.Column("device_type", sa.String(length=20)))
    op.add_column("exam_attempts", sa.Column("user_agent", sa.String(length=500)))
    op.add_column("exam_attempts", sa.Column("started_ip_address", sa.String(length=80)))
    op.add_column("exam_attempts", sa.Column("submitted_ip_address", sa.String(length=80)))


def downgrade() -> None:
    op.drop_column("exam_attempts", "submitted_ip_address")
    op.drop_column("exam_attempts", "started_ip_address")
    op.drop_column("exam_attempts", "user_agent")
    op.drop_column("exam_attempts", "device_type")
