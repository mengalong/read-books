"""增加剧情梗概资料

Revision ID: f1a2b3c4d5e6
Revises: e2f3a4b5c6d7
Create Date: 2026-09-05 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("resource_materials") as batch_op:
        batch_op.add_column(sa.Column("source_registry", sa.JSON(), nullable=True))

    with op.batch_alter_table("questions") as batch_op:
        batch_op.add_column(sa.Column("plot_event_ids", sa.JSON(), nullable=True))

    op.create_table(
        "plot_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("book_id", sa.String(length=36), nullable=False),
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=160), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=True),
        sa.Column("episode_number", sa.Integer(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("future_impact", sa.Text(), nullable=False),
        sa.Column("characters", sa.JSON(), nullable=True),
        sa.Column("relationship_changes", sa.JSON(), nullable=True),
        sa.Column("conflict_tags", sa.JSON(), nullable=True),
        sa.Column("theme_tags", sa.JSON(), nullable=True),
        sa.Column("importance", sa.String(length=20), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("question_usable", sa.String(length=20), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("enabled_for_generation", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["resource_materials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", "event_id", name="uq_plot_event_book_event"),
    )
    op.create_index("ix_plot_events_book_id", "plot_events", ["book_id"])
    op.create_index("ix_plot_events_material_id", "plot_events", ["material_id"])
    op.create_index("ix_plot_events_event_id", "plot_events", ["event_id"])
    op.create_index("ix_plot_events_level", "plot_events", ["level"])
    op.create_index("ix_plot_events_season_number", "plot_events", ["season_number"])
    op.create_index("ix_plot_events_episode_number", "plot_events", ["episode_number"])
    op.create_index("ix_plot_events_confidence", "plot_events", ["confidence"])
    op.create_index("ix_plot_events_question_usable", "plot_events", ["question_usable"])
    op.create_index("ix_plot_events_review_status", "plot_events", ["review_status"])
    op.create_index(
        "ix_plot_events_enabled_for_generation",
        "plot_events",
        ["enabled_for_generation"],
    )


def downgrade() -> None:
    op.drop_index("ix_plot_events_enabled_for_generation", table_name="plot_events")
    op.drop_index("ix_plot_events_review_status", table_name="plot_events")
    op.drop_index("ix_plot_events_question_usable", table_name="plot_events")
    op.drop_index("ix_plot_events_confidence", table_name="plot_events")
    op.drop_index("ix_plot_events_episode_number", table_name="plot_events")
    op.drop_index("ix_plot_events_season_number", table_name="plot_events")
    op.drop_index("ix_plot_events_level", table_name="plot_events")
    op.drop_index("ix_plot_events_event_id", table_name="plot_events")
    op.drop_index("ix_plot_events_material_id", table_name="plot_events")
    op.drop_index("ix_plot_events_book_id", table_name="plot_events")
    op.drop_table("plot_events")

    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_column("plot_event_ids")
    with op.batch_alter_table("resource_materials") as batch_op:
        batch_op.drop_column("source_registry")
