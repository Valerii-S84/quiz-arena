"""m16_add_purchase_funnel_event_metrics

Revision ID: e1f2a3b4c5d6
Revises: f0e1d2c3b4a5
Create Date: 2026-02-20 16:10:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "f0e1d2c3b4a5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analytics_daily",
        sa.Column("purchase_init_events_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "analytics_daily",
        sa.Column(
            "purchase_invoice_sent_events_total",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "analytics_daily",
        sa.Column(
            "purchase_precheckout_ok_events_total",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "analytics_daily",
        sa.Column(
            "purchase_paid_uncredited_events_total",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "analytics_daily",
        sa.Column(
            "purchase_credited_events_total",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.create_check_constraint(
        "ck_analytics_daily_purchase_init_events_non_negative",
        "analytics_daily",
        "purchase_init_events_total >= 0",
    )
    op.create_check_constraint(
        "ck_analytics_daily_purchase_invoice_sent_events_non_negative",
        "analytics_daily",
        "purchase_invoice_sent_events_total >= 0",
    )
    op.create_check_constraint(
        "ck_analytics_daily_purchase_precheckout_ok_events_non_negative",
        "analytics_daily",
        "purchase_precheckout_ok_events_total >= 0",
    )
    op.create_check_constraint(
        "ck_analytics_daily_purchase_paid_uncredited_events_non_negative",
        "analytics_daily",
        "purchase_paid_uncredited_events_total >= 0",
    )
    op.create_check_constraint(
        "ck_analytics_daily_purchase_credited_events_non_negative",
        "analytics_daily",
        "purchase_credited_events_total >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_analytics_daily_purchase_credited_events_non_negative",
        "analytics_daily",
        type_="check",
    )
    op.drop_constraint(
        "ck_analytics_daily_purchase_paid_uncredited_events_non_negative",
        "analytics_daily",
        type_="check",
    )
    op.drop_constraint(
        "ck_analytics_daily_purchase_precheckout_ok_events_non_negative",
        "analytics_daily",
        type_="check",
    )
    op.drop_constraint(
        "ck_analytics_daily_purchase_invoice_sent_events_non_negative",
        "analytics_daily",
        type_="check",
    )
    op.drop_constraint(
        "ck_analytics_daily_purchase_init_events_non_negative",
        "analytics_daily",
        type_="check",
    )
    op.drop_column("analytics_daily", "purchase_credited_events_total")
    op.drop_column("analytics_daily", "purchase_paid_uncredited_events_total")
    op.drop_column("analytics_daily", "purchase_precheckout_ok_events_total")
    op.drop_column("analytics_daily", "purchase_invoice_sent_events_total")
    op.drop_column("analytics_daily", "purchase_init_events_total")
