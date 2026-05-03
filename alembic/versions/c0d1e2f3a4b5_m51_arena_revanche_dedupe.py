"""m51_arena_revanche_dedupe

Revision ID: c0d1e2f3a4b5
Revises: b0c1d2e3f4a5
Create Date: 2026-05-03 12:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c0d1e2f3a4b5"
down_revision: str | None = "b0c1d2e3f4a5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_analytics_events_arena_revanche_once",
        "analytics_events",
        [
            "event_type",
            "user_id",
            sa.text("(payload ->> 'revanche_receiver_id')"),
            sa.text("(payload ->> 'source_attempt_id')"),
            sa.text("(payload ->> 'notification_type')"),
        ],
        unique=True,
        postgresql_where=sa.text(
            "user_id IS NOT NULL "
            "AND payload ? 'revanche_receiver_id' "
            "AND payload ? 'source_attempt_id' "
            "AND payload ? 'notification_type' "
            "AND event_type IN ('arena_revanche_sent')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_analytics_events_arena_revanche_once", table_name="analytics_events")
