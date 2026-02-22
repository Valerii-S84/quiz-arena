"""m19_add_hot_path_indexes

Revision ID: bc34de56f789
Revises: aa12bb34cc56
Create Date: 2026-02-22 15:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bc34de56f789"
down_revision: str | None = "aa12bb34cc56"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_purchases_paid_uncredited_paid_at",
        "purchases",
        ["paid_at"],
        unique=False,
        postgresql_where=sa.text("status = 'PAID_UNCREDITED' AND paid_at IS NOT NULL"),
    )
    op.create_index(
        "idx_purchases_unpaid_created_at",
        "purchases",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('CREATED','INVOICE_SENT') AND paid_at IS NULL"),
    )
    op.create_index(
        "idx_referrals_status_created",
        "referrals",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_referrals_status_qualified_referrer",
        "referrals",
        ["status", "qualified_at", "referrer_user_id"],
        unique=False,
    )
    op.create_index(
        "idx_referrals_referrer_rewarded_at",
        "referrals",
        ["referrer_user_id", "rewarded_at"],
        unique=False,
        postgresql_where=sa.text("status = 'REWARDED' AND rewarded_at IS NOT NULL"),
    )
    op.create_index(
        "idx_outbox_events_type_created_desc",
        "outbox_events",
        ["event_type", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "idx_outbox_events_status_created_desc",
        "outbox_events",
        ["status", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_offers_shown_at",
        "offers_impressions",
        ["shown_at"],
        unique=False,
    )
    op.create_index(
        "idx_offers_shown_at_code",
        "offers_impressions",
        ["shown_at", "offer_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_offers_shown_at_code", table_name="offers_impressions")
    op.drop_index("idx_offers_shown_at", table_name="offers_impressions")
    op.drop_index("idx_outbox_events_status_created_desc", table_name="outbox_events")
    op.drop_index("idx_outbox_events_type_created_desc", table_name="outbox_events")
    op.drop_index("idx_referrals_referrer_rewarded_at", table_name="referrals")
    op.drop_index("idx_referrals_status_qualified_referrer", table_name="referrals")
    op.drop_index("idx_referrals_status_created", table_name="referrals")
    op.drop_index("idx_purchases_unpaid_created_at", table_name="purchases")
    op.drop_index("idx_purchases_paid_uncredited_paid_at", table_name="purchases")
