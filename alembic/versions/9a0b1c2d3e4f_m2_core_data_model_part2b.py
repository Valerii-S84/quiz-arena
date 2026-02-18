"""m2_core_data_model_part2b

Revision ID: 9a0b1c2d3e4f
Revises: 8b7c6d5e4f32
Create Date: 2026-02-18 01:07:30.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9a0b1c2d3e4f"
down_revision: str | None = "8b7c6d5e4f32"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "promo_redemptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("promo_code_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reject_reason", sa.String(64), nullable=True),
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_purchase_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("grant_entitlement_id", sa.BigInteger(), nullable=True),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.Column("validation_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('CREATED','VALIDATED','RESERVED','APPLIED','EXPIRED','REJECTED','REVOKED')", name="ck_promo_redemptions_status"),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["applied_purchase_id"], ["purchases.id"]),
        sa.ForeignKeyConstraint(["grant_entitlement_id"], ["entitlements.id"]),
        sa.UniqueConstraint("applied_purchase_id", name="uq_promo_redemptions_applied_purchase_id"),
        sa.UniqueConstraint("grant_entitlement_id", name="uq_promo_redemptions_grant_entitlement_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_promo_redemptions_idempotency_key"),
        sa.UniqueConstraint("promo_code_id", "user_id", name="uq_promo_redemptions_code_user"),
    )
    op.create_index("idx_promo_redemptions_code", "promo_redemptions", ["promo_code_id"])
    op.create_index("idx_promo_redemptions_user", "promo_redemptions", ["user_id"])
    op.create_index("idx_promo_redemptions_reserved_until", "promo_redemptions", ["reserved_until"])

    op.create_table(
        "promo_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("normalized_code_hash", sa.CHAR(64), nullable=False),
        sa.Column("result", sa.String(24), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("result IN ('ACCEPTED','INVALID','EXPIRED','NOT_APPLICABLE','RATE_LIMITED')", name="ck_promo_attempts_result"),
        sa.CheckConstraint("source IN ('COMMAND','BUTTON','API')", name="ck_promo_attempts_source"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("idx_promo_attempts_user_time", "promo_attempts", ["user_id", "attempted_at"])
    op.create_index("idx_promo_attempts_code_time", "promo_attempts", ["normalized_code_hash", "attempted_at"])

    op.create_table(
        "referrals",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("referrer_user_id", sa.BigInteger(), nullable=False),
        sa.Column("referred_user_id", sa.BigInteger(), nullable=False),
        sa.Column("referral_code", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("qualified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rewarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fraud_score", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('STARTED','QUALIFIED','REWARDED','REJECTED_FRAUD','CANCELED','DEFERRED_LIMIT')", name="ck_referrals_status"),
        sa.CheckConstraint("referrer_user_id <> referred_user_id", name="ck_referrals_no_self_referral"),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.id"]),
        sa.UniqueConstraint("referred_user_id", name="uq_referrals_referred_user_id"),
        sa.UniqueConstraint("referrer_user_id", "referred_user_id", name="uq_referrals_referrer_referred"),
    )
    op.create_index("idx_referrals_referrer", "referrals", ["referrer_user_id"])
    op.create_index("idx_referrals_code", "referrals", ["referral_code"])


def downgrade() -> None:
    op.drop_index("idx_referrals_code", table_name="referrals")
    op.drop_index("idx_referrals_referrer", table_name="referrals")
    op.drop_table("referrals")
    op.drop_index("idx_promo_attempts_code_time", table_name="promo_attempts")
    op.drop_index("idx_promo_attempts_user_time", table_name="promo_attempts")
    op.drop_table("promo_attempts")
    op.drop_index("idx_promo_redemptions_reserved_until", table_name="promo_redemptions")
    op.drop_index("idx_promo_redemptions_user", table_name="promo_redemptions")
    op.drop_index("idx_promo_redemptions_code", table_name="promo_redemptions")
    op.drop_table("promo_redemptions")
