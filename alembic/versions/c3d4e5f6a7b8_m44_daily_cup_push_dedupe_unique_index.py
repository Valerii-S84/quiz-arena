"""m44_daily_cup_push_dedupe_unique_index

Revision ID: c3d4e5f6a7b8
Revises: 0f1e2d3c4b5a
Create Date: 2026-03-10 16:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "0f1e2d3c4b5a"
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
                    'daily_cup_last_call_reminder_sent'
              )
        )
        DELETE FROM analytics_events
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """
    )
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


def downgrade() -> None:
    op.drop_index("uq_analytics_events_daily_cup_push_once", table_name="analytics_events")
