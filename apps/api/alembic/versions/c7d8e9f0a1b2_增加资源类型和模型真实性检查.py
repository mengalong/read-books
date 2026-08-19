"""增加资源类型和模型真实性检查

Revision ID: c7d8e9f0a1b2
Revises: b8c9d0e1f2a3
Create Date: 2026-08-19 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c7d8e9f0a1b2"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("books") as batch_op:
        batch_op.add_column(
            sa.Column(
                "resource_type",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'book'"),
            )
        )
        batch_op.add_column(sa.Column("model_knowledge_supported", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("model_knowledge_message", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("model_knowledge_checked_at", sa.DateTime(timezone=True), nullable=True)
        )
    op.create_index(op.f("ix_books_resource_type"), "books", ["resource_type"], unique=False)
    op.create_index(
        op.f("ix_books_model_knowledge_supported"),
        "books",
        ["model_knowledge_supported"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_books_model_knowledge_supported"), table_name="books")
    op.drop_index(op.f("ix_books_resource_type"), table_name="books")
    with op.batch_alter_table("books") as batch_op:
        batch_op.drop_column("model_knowledge_checked_at")
        batch_op.drop_column("model_knowledge_message")
        batch_op.drop_column("model_knowledge_supported")
        batch_op.drop_column("resource_type")
