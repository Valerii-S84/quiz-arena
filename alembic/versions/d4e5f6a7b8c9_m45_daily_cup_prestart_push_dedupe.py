"""m45_daily_cup_prestart_push_dedupe

Revision ID: d4e5f6a7b8c9
Revises: c5d6e7f8a9b0
Create Date: 2026-04-24 23:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY event_type, user_id, payload ->> 'tournament_id'
                    ORDER BY happened_at ASC, id ASC
                ) AS rn
            FROM analytics_events
            WHERE user_id IS NOT NULL
              AND payload ? 'tournament_id'
              AND event_type IN (
                    'daily_cup_invite_registration_push_sent',
                    'daily_cup_last_call_reminder_sent',
                    'daily_cup_prestart_reminder_sent'
              )
        )
        DELETE FROM analytics_events
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """
    )
    op.drop_index("uq_analytics_events_daily_cup_push_once", table_name="analytics_events")
    op.create_index(
        "uq_analytics_events_daily_cup_push_once",
        "analytics_events",
        ["event_type", "user_id", sa.text("(payload ->> 'tournament_id')")],
        unique=True,
        postgresql_where=sa.text(
            "user_id IS NOT NULL "
            "AND payload ? 'tournament_id' "
            "AND event_type IN "
            "("
            "'daily_cup_invite_registration_push_sent',"
            "'daily_cup_last_call_reminder_sent',"
            "'daily_cup_prestart_reminder_sent'"
            ")"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_analytics_events_daily_cup_push_once", table_name="analytics_events")
    op.create_index(
        "uq_analytics_events_daily_cup_push_once",
        "analytics_events",
        ["event_type", "user_id", sa.text("(payload ->> 'tournament_id')")],
        unique=True,
        postgresql_where=sa.text(
            "user_id IS NOT NULL "
            "AND payload ? 'tournament_id' "
            "AND event_type IN "
            "('daily_cup_invite_registration_push_sent','daily_cup_last_call_reminder_sent')"
        ),
    )
