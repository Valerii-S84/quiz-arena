"""m2_core_data_model_part1b

Revision ID: 4e5f6a7b8c90
Revises: 2f4a1d9c0e11
Create Date: 2026-02-18 01:06:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4e5f6a7b8c90"
down_revision: str | None = "2f4a1d9c0e11"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("asset", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_ledger_entries_amount_positive"),
        sa.CheckConstraint("asset IN ('FREE_ENERGY','PAID_ENERGY','PREMIUM','MODE_ACCESS','STREAK_SAVER')", name="ck_ledger_entries_asset"),
        sa.CheckConstraint("direction IN ('CREDIT','DEBIT')", name="ck_ledger_entries_direction"),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_ledger_entries_idempotency_key"),
    )
    op.create_index("idx_ledger_user_created", "ledger_entries", ["user_id", "created_at"])
    op.create_index("idx_ledger_purchase", "ledger_entries", ["purchase_id"])
    op.create_index("idx_ledger_type", "ledger_entries", ["entry_type"])

    op.create_table(
        "entitlements",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("entitlement_type", sa.String(32), nullable=False),
        sa.Column("scope", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_purchase_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("entitlement_type IN ('PREMIUM','MODE_ACCESS','STREAK_SAVER_TOKEN','PREMIUM_AUTO_FREEZE')", name="ck_entitlements_type"),
        sa.CheckConstraint("status IN ('SCHEDULED','ACTIVE','EXPIRED','CONSUMED','REVOKED')", name="ck_entitlements_status"),
        sa.ForeignKeyConstraint(["source_purchase_id"], ["purchases.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_entitlements_idempotency_key"),
    )
    op.create_index("idx_entitlements_user_type", "entitlements", ["user_id", "entitlement_type"])
    op.create_index("idx_entitlements_starts", "entitlements", ["starts_at"])
    op.create_index("idx_entitlements_ends", "entitlements", ["ends_at"])
    op.create_index("idx_entitlements_purchase", "entitlements", ["source_purchase_id"])
    op.create_index("uq_entitlements_active_premium_per_user", "entitlements", ["user_id"], unique=True, postgresql_where=sa.text("entitlement_type = 'PREMIUM' AND status = 'ACTIVE'"))

    op.create_table(
        "mode_access",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("mode_code", sa.String(32), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_purchase_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source IN ('FREE','MEGA_PACK','PREMIUM')", name="ck_mode_access_source"),
        sa.CheckConstraint("status IN ('ACTIVE','EXPIRED','REVOKED')", name="ck_mode_access_status"),
        sa.ForeignKeyConstraint(["source_purchase_id"], ["purchases.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_mode_access_idempotency_key"),
        sa.UniqueConstraint("user_id", "mode_code", "source", "starts_at", name="uq_mode_access_user_mode_source_starts"),
    )
    op.create_index("idx_mode_access_user_mode", "mode_access", ["user_id", "mode_code"])
    op.create_index("idx_mode_access_mode", "mode_access", ["mode_code"])
    op.create_index("idx_mode_access_ends", "mode_access", ["ends_at"])


def downgrade() -> None:
    op.drop_index("idx_mode_access_ends", table_name="mode_access")
    op.drop_index("idx_mode_access_mode", table_name="mode_access")
    op.drop_index("idx_mode_access_user_mode", table_name="mode_access")
    op.drop_table("mode_access")
    op.drop_index("uq_entitlements_active_premium_per_user", table_name="entitlements")
    op.drop_index("idx_entitlements_purchase", table_name="entitlements")
    op.drop_index("idx_entitlements_ends", table_name="entitlements")
    op.drop_index("idx_entitlements_starts", table_name="entitlements")
    op.drop_index("idx_entitlements_user_type", table_name="entitlements")
    op.drop_table("entitlements")
    op.drop_index("idx_ledger_type", table_name="ledger_entries")
    op.drop_index("idx_ledger_purchase", table_name="ledger_entries")
    op.drop_index("idx_ledger_user_created", table_name="ledger_entries")
    op.drop_table("ledger_entries")
