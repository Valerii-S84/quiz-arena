"""m15_add_analytics_tables

Revision ID: f0e1d2c3b4a5
Revises: d5e6f7a8b9c0
Create Date: 2026-02-20 14:35:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f0e1d2c3b4a5"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("local_date_berlin", sa.Date(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("happened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "source IN ('BOT','WORKER','API','SYSTEM')",
            name="ck_analytics_events_source",
        ),
    )
    op.create_index("idx_analytics_events_type_time", "analytics_events", ["event_type", "happened_at"])
    op.create_index("idx_analytics_events_user_time", "analytics_events", ["user_id", "happened_at"])
    op.create_index(
        "idx_analytics_events_local_date_type",
        "analytics_events",
        ["local_date_berlin", "event_type"],
    )

    op.create_table(
        "analytics_daily",
        sa.Column("local_date_berlin", sa.Date(), primary_key=True),
        sa.Column("dau", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("wau", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("mau", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("purchases_credited_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("purchasers_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("purchase_rate", sa.Numeric(8, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("promo_redemptions_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("promo_redemptions_applied_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("promo_redemption_rate", sa.Numeric(8, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("promo_to_paid_conversions_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("quiz_sessions_started_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("quiz_sessions_completed_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("gameplay_completion_rate", sa.Numeric(8, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("energy_zero_events_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("streak_lost_events_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("referral_reward_milestone_events_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("referral_reward_granted_events_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("dau >= 0", name="ck_analytics_daily_dau_non_negative"),
        sa.CheckConstraint("wau >= 0", name="ck_analytics_daily_wau_non_negative"),
        sa.CheckConstraint("mau >= 0", name="ck_analytics_daily_mau_non_negative"),
        sa.CheckConstraint(
            "purchases_credited_total >= 0",
            name="ck_analytics_daily_purchases_credited_non_negative",
        ),
        sa.CheckConstraint("purchasers_total >= 0", name="ck_analytics_daily_purchasers_non_negative"),
        sa.CheckConstraint(
            "promo_redemptions_total >= 0",
            name="ck_analytics_daily_promo_redemptions_non_negative",
        ),
        sa.CheckConstraint(
            "promo_redemptions_applied_total >= 0",
            name="ck_analytics_daily_promo_redemptions_applied_non_negative",
        ),
        sa.CheckConstraint(
            "promo_to_paid_conversions_total >= 0",
            name="ck_analytics_daily_promo_to_paid_non_negative",
        ),
        sa.CheckConstraint(
            "quiz_sessions_started_total >= 0",
            name="ck_analytics_daily_sessions_started_non_negative",
        ),
        sa.CheckConstraint(
            "quiz_sessions_completed_total >= 0",
            name="ck_analytics_daily_sessions_completed_non_negative",
        ),
        sa.CheckConstraint(
            "energy_zero_events_total >= 0",
            name="ck_analytics_daily_energy_zero_non_negative",
        ),
        sa.CheckConstraint(
            "streak_lost_events_total >= 0",
            name="ck_analytics_daily_streak_lost_non_negative",
        ),
        sa.CheckConstraint(
            "referral_reward_milestone_events_total >= 0",
            name="ck_analytics_daily_referral_milestone_non_negative",
        ),
        sa.CheckConstraint(
            "referral_reward_granted_events_total >= 0",
            name="ck_analytics_daily_referral_granted_non_negative",
        ),
        sa.CheckConstraint(
            "purchase_rate >= 0 AND purchase_rate <= 1",
            name="ck_analytics_daily_purchase_rate",
        ),
        sa.CheckConstraint(
            "promo_redemption_rate >= 0 AND promo_redemption_rate <= 1",
            name="ck_analytics_daily_promo_redemption_rate",
        ),
        sa.CheckConstraint(
            "gameplay_completion_rate >= 0 AND gameplay_completion_rate <= 1",
            name="ck_analytics_daily_gameplay_completion_rate",
        ),
    )
    op.create_index("idx_analytics_daily_calculated_at", "analytics_daily", ["calculated_at"])


def downgrade() -> None:
    op.drop_index("idx_analytics_daily_calculated_at", table_name="analytics_daily")
    op.drop_table("analytics_daily")
    op.drop_index("idx_analytics_events_local_date_type", table_name="analytics_events")
    op.drop_index("idx_analytics_events_user_time", table_name="analytics_events")
    op.drop_index("idx_analytics_events_type_time", table_name="analytics_events")
    op.drop_table("analytics_events")
