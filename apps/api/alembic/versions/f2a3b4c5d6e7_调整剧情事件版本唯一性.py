"""调整剧情事件版本唯一性

Revision ID: f2a3b4c5d6e7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-05 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    unique_names = {
        constraint.get("name") for constraint in inspector.get_unique_constraints("plot_events")
    }
    if "uq_plot_event_book_event" not in unique_names and "uq_plot_event_material_event" in unique_names:
        return
    with op.batch_alter_table("plot_events") as batch_op:
        if "uq_plot_event_book_event" in unique_names:
            batch_op.drop_constraint("uq_plot_event_book_event", type_="unique")
        batch_op.create_unique_constraint(
            "uq_plot_event_material_event", ["material_id", "event_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("plot_events") as batch_op:
        batch_op.drop_constraint("uq_plot_event_material_event", type_="unique")
        batch_op.create_unique_constraint(
            "uq_plot_event_book_event", ["book_id", "event_id"]
        )
