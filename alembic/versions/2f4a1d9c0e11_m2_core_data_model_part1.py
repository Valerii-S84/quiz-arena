"""m2_core_data_model_part1

Revision ID: 2f4a1d9c0e11
Revises: 1c7257851be3
Create Date: 2026-02-18 01:05:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2f4a1d9c0e11"
down_revision: str | None = "1c7257851be3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("first_name", sa.Text(), nullable=True),
        sa.Column("language_code", sa.String(8), nullable=False, server_default=sa.text("'de'")),
        sa.Column("timezone", sa.String(64), nullable=False, server_default=sa.text("'Europe/Berlin'")),
        sa.Column("referral_code", sa.String(16), nullable=False),
        sa.Column("referred_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('ACTIVE','BLOCKED','DELETED')", name="ck_users_status"),
        sa.ForeignKeyConstraint(["referred_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("telegram_user_id", name="uq_users_telegram_user_id"),
        sa.UniqueConstraint("referral_code", name="uq_users_referral_code"),
    )
    op.create_index("idx_users_username", "users", ["username"])
    op.create_index("idx_users_referred_by", "users", ["referred_by_user_id"])
    op.create_index("idx_users_created_at", "users", ["created_at"])
    op.create_index("idx_users_last_seen", "users", ["last_seen_at"])

    op.create_table(
        "energy_state",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("free_energy", sa.SmallInteger(), nullable=False),
        sa.Column("paid_energy", sa.Integer(), nullable=False),
        sa.Column("free_cap", sa.SmallInteger(), nullable=False, server_default=sa.text("20")),
        sa.Column("regen_interval_sec", sa.Integer(), nullable=False, server_default=sa.text("1800")),
        sa.Column("last_regen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_daily_topup_local_date", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("free_energy >= 0 AND free_energy <= 20", name="ck_energy_state_free_energy_range"),
        sa.CheckConstraint("paid_energy >= 0", name="ck_energy_state_paid_energy_non_negative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("idx_energy_last_regen", "energy_state", ["last_regen_at"])
    op.create_index("idx_energy_topup_date", "energy_state", ["last_daily_topup_local_date"])

    op.create_table(
        "streak_state",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("current_streak", sa.Integer(), nullable=False),
        sa.Column("best_streak", sa.Integer(), nullable=False),
        sa.Column("last_activity_local_date", sa.Date(), nullable=True),
        sa.Column("today_status", sa.String(16), nullable=False),
        sa.Column("streak_saver_tokens", sa.SmallInteger(), nullable=False),
        sa.Column("streak_saver_last_purchase_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("premium_freezes_used_week", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("premium_freeze_week_start_local_date", sa.Date(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("current_streak >= 0", name="ck_streak_state_current_streak_non_negative"),
        sa.CheckConstraint("best_streak >= 0", name="ck_streak_state_best_streak_non_negative"),
        sa.CheckConstraint("streak_saver_tokens >= 0", name="ck_streak_state_tokens_non_negative"),
        sa.CheckConstraint("today_status IN ('NO_ACTIVITY','PLAYED','FROZEN')", name="ck_streak_state_today_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("idx_streak_last_activity", "streak_state", ["last_activity_local_date"])
    op.create_index("idx_streak_saver_purchase", "streak_state", ["streak_saver_last_purchase_at"])

    op.create_table(
        "purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_code", sa.String(32), nullable=False),
        sa.Column("product_type", sa.String(16), nullable=False),
        sa.Column("base_stars_amount", sa.Integer(), nullable=False),
        sa.Column("discount_stars_amount", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("stars_amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'XTR'")),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("applied_promo_code_id", sa.BigInteger(), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("invoice_payload", sa.String(128), nullable=False),
        sa.Column("telegram_payment_charge_id", sa.String(128), nullable=True),
        sa.Column("telegram_pre_checkout_query_id", sa.String(128), nullable=True),
        sa.Column("raw_successful_payment", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("product_type IN ('MICRO','PREMIUM','OFFER','REFERRAL_REWARD')", name="ck_purchases_product_type"),
        sa.CheckConstraint("base_stars_amount > 0", name="ck_purchases_base_amount_positive"),
        sa.CheckConstraint("discount_stars_amount >= 0", name="ck_purchases_discount_non_negative"),
        sa.CheckConstraint("stars_amount > 0", name="ck_purchases_stars_amount_positive"),
        sa.CheckConstraint("status IN ('CREATED','INVOICE_SENT','PRECHECKOUT_OK','PAID_UNCREDITED','CREDITED','FAILED','FAILED_CREDIT_PENDING_REVIEW','REFUNDED')", name="ck_purchases_status"),
        sa.CheckConstraint("stars_amount = GREATEST(1, base_stars_amount - discount_stars_amount)", name="ck_purchases_final_amount"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_purchases_idempotency_key"),
        sa.UniqueConstraint("invoice_payload", name="uq_purchases_invoice_payload"),
        sa.UniqueConstraint("telegram_payment_charge_id", name="uq_purchases_telegram_payment_charge_id"),
        sa.UniqueConstraint("telegram_pre_checkout_query_id", name="uq_purchases_telegram_pre_checkout_query_id"),
    )
    op.create_index("idx_purchases_user_created", "purchases", ["user_id", "created_at"])
    op.create_index("idx_purchases_product", "purchases", ["product_code"])
    op.create_index("idx_purchases_promo_code", "purchases", ["applied_promo_code_id"])


def downgrade() -> None:
    op.drop_index("idx_purchases_promo_code", table_name="purchases")
    op.drop_index("idx_purchases_product", table_name="purchases")
    op.drop_index("idx_purchases_user_created", table_name="purchases")
    op.drop_table("purchases")
    op.drop_index("idx_streak_saver_purchase", table_name="streak_state")
    op.drop_index("idx_streak_last_activity", table_name="streak_state")
    op.drop_table("streak_state")
    op.drop_index("idx_energy_topup_date", table_name="energy_state")
    op.drop_index("idx_energy_last_regen", table_name="energy_state")
    op.drop_table("energy_state")
    op.drop_index("idx_users_last_seen", table_name="users")
    op.drop_index("idx_users_created_at", table_name="users")
    op.drop_index("idx_users_referred_by", table_name="users")
    op.drop_index("idx_users_username", table_name="users")
    op.drop_table("users")
