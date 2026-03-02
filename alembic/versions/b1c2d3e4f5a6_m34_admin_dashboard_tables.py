"""m34_admin_dashboard_tables

Revision ID: b1c2d3e4f5a6
Revises: a3b4c5d6e7f8
Create Date: 2026-03-02 18:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_metrics",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("dau", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("wau", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("mau", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("new_users", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("revenue_stars", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("revenue_eur", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("quizzes_played", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("purchases_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active_subscriptions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("dau >= 0", name="ck_daily_metrics_dau_non_negative"),
        sa.CheckConstraint("wau >= 0", name="ck_daily_metrics_wau_non_negative"),
        sa.CheckConstraint("mau >= 0", name="ck_daily_metrics_mau_non_negative"),
        sa.CheckConstraint("new_users >= 0", name="ck_daily_metrics_new_users_non_negative"),
        sa.CheckConstraint("revenue_stars >= 0", name="ck_daily_metrics_revenue_stars_non_negative"),
        sa.CheckConstraint("revenue_eur >= 0", name="ck_daily_metrics_revenue_eur_non_negative"),
        sa.CheckConstraint("quizzes_played >= 0", name="ck_daily_metrics_quizzes_non_negative"),
        sa.CheckConstraint("purchases_count >= 0", name="ck_daily_metrics_purchases_non_negative"),
        sa.CheckConstraint(
            "active_subscriptions >= 0",
            name="ck_daily_metrics_active_subscriptions_non_negative",
        ),
    )

    op.create_table(
        "admin_promo_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("promo_type", sa.String(30), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("product_code", sa.String(32), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("uses_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channel_tag", sa.String(50), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "promo_type IN ('discount_percent','discount_stars','bonus_energy','bonus_subscription_days','free_product')",  # noqa: E501
            name="ck_admin_promo_codes_type",
        ),
        sa.CheckConstraint(
            "status IN ('active','paused','expired','archived')",
            name="ck_admin_promo_codes_status",
        ),
        sa.CheckConstraint("value >= 0", name="ck_admin_promo_codes_value_non_negative"),
        sa.CheckConstraint("max_uses >= 0", name="ck_admin_promo_codes_max_uses_non_negative"),
        sa.CheckConstraint("uses_count >= 0", name="ck_admin_promo_codes_uses_non_negative"),
        sa.UniqueConstraint("code", name="uq_admin_promo_codes_code"),
    )

    op.create_table(
        "admin_promo_code_usages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("promo_code_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["promo_code_id"],
            ["admin_promo_codes.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_admin_promo_code_usages_code",
        "admin_promo_code_usages",
        ["promo_code_id"],
    )
    op.create_index(
        "idx_admin_promo_code_usages_user_used",
        "admin_promo_code_usages",
        ["user_id", "used_at"],
    )

    op.create_table(
        "user_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_user_events_user_created_desc",
        "user_events",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_user_events_type_created",
        "user_events",
        ["event_type", "created_at"],
    )

    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("admin_email", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_admin_audit_log_created_at", "admin_audit_log", ["created_at"])
    op.create_index("idx_admin_audit_log_action", "admin_audit_log", ["action", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_admin_audit_log_action", table_name="admin_audit_log")
    op.drop_index("idx_admin_audit_log_created_at", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")

    op.drop_index("idx_user_events_type_created", table_name="user_events")
    op.drop_index("idx_user_events_user_created_desc", table_name="user_events")
    op.drop_table("user_events")

    op.drop_index("idx_admin_promo_code_usages_user_used", table_name="admin_promo_code_usages")
    op.drop_index("idx_admin_promo_code_usages_code", table_name="admin_promo_code_usages")
    op.drop_table("admin_promo_code_usages")

    op.drop_table("admin_promo_codes")
    op.drop_table("daily_metrics")
