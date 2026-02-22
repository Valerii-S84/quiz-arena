"""m21_add_retention_cleanup_indexes

Revision ID: de56fa78bc90
Revises: cd45ef678901
Create Date: 2026-02-22 19:40:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "de56fa78bc90"
down_revision: str | None = "cd45ef678901"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_processed_updates_processed_at",
        "processed_updates",
        ["processed_at"],
        unique=False,
    )
    op.create_index(
        "idx_outbox_events_created_at",
        "outbox_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "idx_analytics_events_created_at",
        "analytics_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_analytics_events_created_at", table_name="analytics_events")
    op.drop_index("idx_outbox_events_created_at", table_name="outbox_events")
    op.drop_index("idx_processed_updates_processed_at", table_name="processed_updates")
