"""m2_core_data_model_part2

Revision ID: 8b7c6d5e4f32
Revises: 4e5f6a7b8c90
Create Date: 2026-02-18 01:07:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8b7c6d5e4f32"
down_revision: str | None = "4e5f6a7b8c90"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quiz_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("mode_code", sa.String(32), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("energy_cost_total", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("local_date_berlin", sa.Date(), nullable=False),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.CheckConstraint("source IN ('MENU','DAILY_CHALLENGE','FRIEND_CHALLENGE','TOURNAMENT')", name="ck_quiz_sessions_source"),
        sa.CheckConstraint("status IN ('STARTED','COMPLETED','ABANDONED','CANCELED')", name="ck_quiz_sessions_status"),
        sa.CheckConstraint("energy_cost_total >= 0", name="ck_quiz_sessions_energy_cost_non_negative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_quiz_sessions_idempotency_key"),
    )
    op.create_index("idx_sessions_user_started", "quiz_sessions", ["user_id", "started_at"])
    op.create_index("idx_sessions_mode", "quiz_sessions", ["mode_code"])
    op.create_index("idx_sessions_local_date", "quiz_sessions", ["local_date_berlin"])

    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("question_id", sa.String(64), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_ms", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.CheckConstraint("response_ms >= 0", name="ck_quiz_attempts_response_ms_non_negative"),
        sa.ForeignKeyConstraint(["session_id"], ["quiz_sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_quiz_attempts_idempotency_key"),
    )
    op.create_index("idx_attempts_session", "quiz_attempts", ["session_id"])
    op.create_index("idx_attempts_user_time", "quiz_attempts", ["user_id", "answered_at"])
    op.create_index("idx_attempts_question", "quiz_attempts", ["question_id"])

    op.create_table(
        "offers_impressions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_code", sa.String(32), nullable=False),
        sa.Column("trigger_code", sa.String(32), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_date_berlin", sa.Date(), nullable=False),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_purchase_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dismiss_reason", sa.String(32), nullable=True),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.ForeignKeyConstraint(["converted_purchase_id"], ["purchases.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_offers_impressions_idempotency_key"),
    )
    op.create_index("idx_offers_user_time", "offers_impressions", ["user_id", "shown_at"])
    op.create_index("idx_offers_code", "offers_impressions", ["offer_code"])
    op.create_index("idx_offers_local_date", "offers_impressions", ["local_date_berlin"])

    op.create_table(
        "promo_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code_hash", sa.CHAR(64), nullable=False),
        sa.Column("code_prefix", sa.String(8), nullable=False),
        sa.Column("campaign_name", sa.String(128), nullable=False),
        sa.Column("promo_type", sa.String(32), nullable=False),
        sa.Column("grant_premium_days", sa.SmallInteger(), nullable=True),
        sa.Column("discount_percent", sa.SmallInteger(), nullable=True),
        sa.Column("target_scope", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_total_uses", sa.Integer(), nullable=True),
        sa.Column("used_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_uses_per_user", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("new_users_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("first_purchase_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("promo_type IN ('PREMIUM_GRANT','PERCENT_DISCOUNT')", name="ck_promo_codes_type"),
        sa.CheckConstraint("grant_premium_days IS NULL OR grant_premium_days IN (7,30,90)", name="ck_promo_codes_grant_days"),
        sa.CheckConstraint("discount_percent IS NULL OR (discount_percent BETWEEN 1 AND 90)", name="ck_promo_codes_discount_percent"),
        sa.CheckConstraint("status IN ('ACTIVE','PAUSED','EXPIRED','DEPLETED')", name="ck_promo_codes_status"),
        sa.CheckConstraint("max_total_uses IS NULL OR max_total_uses > 0", name="ck_promo_codes_max_total_uses_positive"),
        sa.CheckConstraint("used_total >= 0", name="ck_promo_codes_used_total_non_negative"),
        sa.CheckConstraint("max_uses_per_user = 1", name="ck_promo_codes_max_uses_per_user_is_one"),
        sa.CheckConstraint("((promo_type = 'PREMIUM_GRANT' AND grant_premium_days IS NOT NULL AND discount_percent IS NULL) OR (promo_type = 'PERCENT_DISCOUNT' AND discount_percent IS NOT NULL AND grant_premium_days IS NULL))", name="ck_promo_codes_type_payload_consistency"),
        sa.CheckConstraint("max_total_uses IS NULL OR used_total <= max_total_uses", name="ck_promo_codes_used_total_le_max"),
        sa.UniqueConstraint("code_hash", name="uq_promo_codes_code_hash"),
    )
    op.create_index("idx_promo_codes_prefix", "promo_codes", ["code_prefix"])
    op.create_index("idx_promo_codes_target", "promo_codes", ["target_scope"])
    op.create_index("idx_promo_codes_valid_from", "promo_codes", ["valid_from"])
    op.create_index("idx_promo_codes_valid_until", "promo_codes", ["valid_until"])
    op.create_foreign_key("fk_purchases_applied_promo_code_id_promo_codes", "purchases", "promo_codes", ["applied_promo_code_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_purchases_applied_promo_code_id_promo_codes", "purchases", type_="foreignkey")
    op.drop_index("idx_promo_codes_valid_until", table_name="promo_codes")
    op.drop_index("idx_promo_codes_valid_from", table_name="promo_codes")
    op.drop_index("idx_promo_codes_target", table_name="promo_codes")
    op.drop_index("idx_promo_codes_prefix", table_name="promo_codes")
    op.drop_table("promo_codes")
    op.drop_index("idx_offers_local_date", table_name="offers_impressions")
    op.drop_index("idx_offers_code", table_name="offers_impressions")
    op.drop_index("idx_offers_user_time", table_name="offers_impressions")
    op.drop_table("offers_impressions")
    op.drop_index("idx_attempts_question", table_name="quiz_attempts")
    op.drop_index("idx_attempts_user_time", table_name="quiz_attempts")
    op.drop_index("idx_attempts_session", table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
    op.drop_index("idx_sessions_local_date", table_name="quiz_sessions")
    op.drop_index("idx_sessions_mode", table_name="quiz_sessions")
    op.drop_index("idx_sessions_user_started", table_name="quiz_sessions")
    op.drop_table("quiz_sessions")
