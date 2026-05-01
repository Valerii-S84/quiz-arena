"""m48_arena_beaten_notification_dedupe

Revision ID: f8a9b0c1d2e3
Revises: f7a8b9c0d1e2
Create Date: 2026-05-01 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_index(
        "uq_analytics_events_arena_beaten_notice_once",
        "analytics_events",
        [
            "event_type",
            "user_id",
            sa.text("(payload ->> 'arena_duel_id')"),
            sa.text("(payload ->> 'previous_best_attempt_id')"),
            sa.text("(payload ->> 'new_best_attempt_id')"),
            sa.text("(payload ->> 'notification_type')"),
        ],
        unique=True,
        postgresql_where=sa.text(
            "user_id IS NOT NULL "
            "AND payload ? 'arena_duel_id' "
            "AND payload ? 'previous_best_attempt_id' "
            "AND payload ? 'new_best_attempt_id' "
            "AND payload ? 'notification_type' "
            "AND event_type IN ('arena_result_beaten_notification_sent')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_analytics_events_arena_beaten_notice_once",
        table_name="analytics_events",
    )
