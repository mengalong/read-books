"""增加微信考试身份认证

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-06 23:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wechat_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("openid", sa.String(length=128), nullable=False),
        sa.Column("unionid", sa.String(length=128), nullable=True),
        sa.Column("nickname", sa.String(length=120), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wechat_users_openid", "wechat_users", ["openid"], unique=True)
    op.create_index("ix_wechat_users_unionid", "wechat_users", ["unionid"], unique=True)
    op.create_index(
        "ix_wechat_users_last_login_at",
        "wechat_users",
        ["last_login_at"],
        unique=False,
    )

    op.create_table(
        "wechat_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("wechat_user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("ip_address", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["wechat_user_id"], ["wechat_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wechat_sessions_wechat_user_id",
        "wechat_sessions",
        ["wechat_user_id"],
        unique=False,
    )
    op.create_index("ix_wechat_sessions_token_hash", "wechat_sessions", ["token_hash"], unique=True)
    op.create_index("ix_wechat_sessions_expires_at", "wechat_sessions", ["expires_at"], unique=False)
    op.create_index("ix_wechat_sessions_revoked_at", "wechat_sessions", ["revoked_at"], unique=False)

    op.create_table(
        "wechat_oauth_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("state_hash", sa.String(length=128), nullable=False),
        sa.Column("browser_nonce_hash", sa.String(length=128), nullable=False),
        sa.Column("share_code", sa.String(length=80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_ip_address", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wechat_oauth_states_state_hash",
        "wechat_oauth_states",
        ["state_hash"],
        unique=True,
    )
    op.create_index(
        "ix_wechat_oauth_states_share_code",
        "wechat_oauth_states",
        ["share_code"],
        unique=False,
    )
    op.create_index(
        "ix_wechat_oauth_states_expires_at",
        "wechat_oauth_states",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_wechat_oauth_states_consumed_at",
        "wechat_oauth_states",
        ["consumed_at"],
        unique=False,
    )

    op.create_table(
        "wechat_login_configurations",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("required_for_public_exams", sa.Boolean(), nullable=False),
        sa.Column("app_id", sa.String(length=128), nullable=False),
        sa.Column("app_secret", sa.Text(), nullable=True),
        sa.Column("callback_base_url", sa.Text(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wechat_login_configurations_updated_by_user_id",
        "wechat_login_configurations",
        ["updated_by_user_id"],
        unique=False,
    )

    with op.batch_alter_table("exam_attempts") as batch_op:
        batch_op.add_column(sa.Column("participant_wechat_user_id", sa.String(length=36)))
        batch_op.add_column(sa.Column("participant_avatar_url", sa.Text()))
        batch_op.create_foreign_key(
            "fk_exam_attempts_wechat_user",
            "wechat_users",
            ["participant_wechat_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_exam_attempt_share_wechat",
            ["exam_share_id", "participant_wechat_user_id"],
        )
        batch_op.create_index(
            "ix_exam_attempts_participant_wechat_user_id",
            ["participant_wechat_user_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("exam_attempts") as batch_op:
        batch_op.drop_index("ix_exam_attempts_participant_wechat_user_id")
        batch_op.drop_constraint("uq_exam_attempt_share_wechat", type_="unique")
        batch_op.drop_constraint("fk_exam_attempts_wechat_user", type_="foreignkey")
        batch_op.drop_column("participant_avatar_url")
        batch_op.drop_column("participant_wechat_user_id")

    op.drop_index(
        "ix_wechat_login_configurations_updated_by_user_id",
        table_name="wechat_login_configurations",
    )
    op.drop_table("wechat_login_configurations")
    op.drop_index("ix_wechat_oauth_states_consumed_at", table_name="wechat_oauth_states")
    op.drop_index("ix_wechat_oauth_states_expires_at", table_name="wechat_oauth_states")
    op.drop_index("ix_wechat_oauth_states_share_code", table_name="wechat_oauth_states")
    op.drop_index("ix_wechat_oauth_states_state_hash", table_name="wechat_oauth_states")
    op.drop_table("wechat_oauth_states")
    op.drop_index("ix_wechat_sessions_revoked_at", table_name="wechat_sessions")
    op.drop_index("ix_wechat_sessions_expires_at", table_name="wechat_sessions")
    op.drop_index("ix_wechat_sessions_token_hash", table_name="wechat_sessions")
    op.drop_index("ix_wechat_sessions_wechat_user_id", table_name="wechat_sessions")
    op.drop_table("wechat_sessions")
    op.drop_index("ix_wechat_users_last_login_at", table_name="wechat_users")
    op.drop_index("ix_wechat_users_unionid", table_name="wechat_users")
    op.drop_index("ix_wechat_users_openid", table_name="wechat_users")
    op.drop_table("wechat_users")
