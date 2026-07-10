"""m55_payment_reliability_inbox_events

Revision ID: ac12bd34ef56
Revises: 9b8c7d6e5f4a
Create Date: 2026-07-09 23:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ac12bd34ef56"
down_revision: str | None = "9b8c7d6e5f4a"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_update_inbox",
        sa.Column("update_id", sa.BigInteger(), primary_key=True),
        sa.Column("update_kind", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("sanitized_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default=sa.text("'RECEIVED'")
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_type", sa.String(length=128), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_telegram_update_inbox_idempotency_key"),
    )
    op.create_index(
        "idx_telegram_update_inbox_status_received",
        "telegram_update_inbox",
        ["status", "received_at"],
    )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default=sa.text("'RECEIVED'")
        ),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("source_inbox_update_id", sa.BigInteger(), nullable=True),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("invoice_payload", sa.String(length=128), nullable=True),
        sa.Column("provider_charge_id_hash", sa.String(length=64), nullable=True),
        sa.Column("provider_payment_charge_id_hash", sa.String(length=64), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("total_amount", sa.BigInteger(), nullable=True),
        sa.Column(
            "safe_payload",
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
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_type", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["source_inbox_update_id"], ["telegram_update_inbox.update_id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_payment_events_idempotency_key"),
    )
    op.create_index("idx_payment_events_status_created", "payment_events", ["status", "created_at"])
    op.create_index("idx_payment_events_invoice_payload", "payment_events", ["invoice_payload"])
    op.create_index(
        "idx_payment_events_provider_charge_hash",
        "payment_events",
        ["provider_charge_id_hash"],
    )

    op.create_table(
        "payment_reconciliation_reviews",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("unique_key", sa.String(length=160), nullable=False),
        sa.Column("review_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'OPEN'")),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("payment_event_id", sa.BigInteger(), nullable=True),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transaction_id_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "safe_payload",
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
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["payment_event_id"], ["payment_events.id"]),
        sa.UniqueConstraint("unique_key", name="uq_payment_reconciliation_reviews_unique_key"),
    )
    op.create_index(
        "idx_payment_reconciliation_reviews_status_created",
        "payment_reconciliation_reviews",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_payment_reconciliation_reviews_purchase",
        "payment_reconciliation_reviews",
        ["purchase_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_payment_reconciliation_reviews_purchase",
        table_name="payment_reconciliation_reviews",
    )
    op.drop_index(
        "idx_payment_reconciliation_reviews_status_created",
        table_name="payment_reconciliation_reviews",
    )
    op.drop_table("payment_reconciliation_reviews")
    op.drop_index("idx_payment_events_provider_charge_hash", table_name="payment_events")
    op.drop_index("idx_payment_events_invoice_payload", table_name="payment_events")
    op.drop_index("idx_payment_events_status_created", table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_index("idx_telegram_update_inbox_status_received", table_name="telegram_update_inbox")
    op.drop_table("telegram_update_inbox")
