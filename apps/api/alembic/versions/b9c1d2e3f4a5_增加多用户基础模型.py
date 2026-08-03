"""增加多用户基础模型

Revision ID: b9c1d2e3f4a5
Revises: e1f2a3b4c5d6
Create Date: 2026-08-04 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column.name not in existing:
        op.add_column(table_name, column)


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if name not in existing:
        op.create_index(name, table_name, columns)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("username", sa.String(length=80), nullable=False),
            sa.Column("display_name", sa.String(length=120), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("must_change_password", sa.Boolean(), nullable=False),
            sa.Column("failed_login_count", sa.Integer(), nullable=False),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username"),
        )
        op.create_index("ix_users_username", "users", ["username"])
        op.create_index("ix_users_role", "users", ["role"])
        op.create_index("ix_users_status", "users", ["status"])

    if "workspaces" not in tables:
        op.create_table(
            "workspaces",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("workspace_type", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_workspaces_created_by_user_id", "workspaces", ["created_by_user_id"]
        )
        op.create_index("ix_workspaces_status", "workspaces", ["status"])

    if "workspace_members" not in tables:
        op.create_table(
            "workspace_members",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("workspace_id", "user_id"),
        )
        op.create_index(
            "ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"]
        )
        op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])

    if "user_sessions" not in tables:
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("user_agent", sa.String(length=500), nullable=True),
            sa.Column("ip_address", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
        op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"])
        op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])

    if "audit_logs" not in tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("actor_user_id", sa.String(length=36), nullable=True),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("target_type", sa.String(length=50), nullable=False),
            sa.Column("target_id", sa.String(length=36), nullable=True),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("ip_address", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["actor_user_id"], ["users.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("actor_user_id", "action", "target_type", "target_id", "created_at"):
            op.create_index(f"ix_audit_logs_{column}", "audit_logs", [column])

    _add_column_if_missing(
        "books", sa.Column("workspace_id", sa.String(length=36), nullable=True)
    )
    _add_column_if_missing(
        "books", sa.Column("created_by_user_id", sa.String(length=36), nullable=True)
    )
    _add_column_if_missing(
        "quiz_generation_tasks",
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
    )
    _add_column_if_missing(
        "model_usage_records", sa.Column("workspace_id", sa.String(length=36), nullable=True)
    )
    _add_column_if_missing(
        "model_usage_records", sa.Column("user_id", sa.String(length=36), nullable=True)
    )
    _add_column_if_missing(
        "model_configurations",
        sa.Column("scope_type", sa.String(length=20), nullable=True, server_default="platform"),
    )
    _add_column_if_missing(
        "model_configurations", sa.Column("workspace_id", sa.String(length=36), nullable=True)
    )
    _add_column_if_missing(
        "model_configurations",
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
    )
    _add_column_if_missing(
        "prompt_templates",
        sa.Column("scope_type", sa.String(length=20), nullable=True, server_default="platform"),
    )
    _add_column_if_missing(
        "prompt_templates", sa.Column("workspace_id", sa.String(length=36), nullable=True)
    )
    _add_column_if_missing(
        "prompt_templates", sa.Column("updated_by_user_id", sa.String(length=36), nullable=True)
    )

    for table_name, column_name in (
        ("books", "workspace_id"),
        ("books", "created_by_user_id"),
        ("quiz_generation_tasks", "created_by_user_id"),
        ("model_usage_records", "workspace_id"),
        ("model_usage_records", "user_id"),
        ("model_configurations", "scope_type"),
        ("model_configurations", "workspace_id"),
        ("model_configurations", "updated_by_user_id"),
        ("prompt_templates", "scope_type"),
        ("prompt_templates", "workspace_id"),
        ("prompt_templates", "updated_by_user_id"),
    ):
        _create_index_if_missing(
            f"ix_{table_name}_{column_name}", table_name, [column_name]
        )


def downgrade() -> None:
    # Ownership columns remain nullable so an older application can still read the data.
    for table_name, column_name in (
        ("prompt_templates", "updated_by_user_id"),
        ("prompt_templates", "workspace_id"),
        ("prompt_templates", "scope_type"),
        ("model_configurations", "updated_by_user_id"),
        ("model_configurations", "workspace_id"),
        ("model_configurations", "scope_type"),
        ("model_usage_records", "user_id"),
        ("model_usage_records", "workspace_id"),
        ("quiz_generation_tasks", "created_by_user_id"),
        ("books", "created_by_user_id"),
        ("books", "workspace_id"),
    ):
        inspector = sa.inspect(op.get_bind())
        if column_name in {item["name"] for item in inspector.get_columns(table_name)}:
            index_name = f"ix_{table_name}_{column_name}"
            if index_name in {item["name"] for item in inspector.get_indexes(table_name)}:
                op.drop_index(index_name, table_name=table_name)
            op.drop_column(table_name, column_name)

    for table_name in ("audit_logs", "user_sessions", "workspace_members", "workspaces", "users"):
        if sa.inspect(op.get_bind()).has_table(table_name):
            op.drop_table(table_name)
