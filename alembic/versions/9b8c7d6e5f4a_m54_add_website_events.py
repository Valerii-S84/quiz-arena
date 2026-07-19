"""m54_add_website_events

Revision ID: 9b8c7d6e5f4a
Revises: e7f8a9b0c2d3
Create Date: 2026-06-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9b8c7d6e5f4a"
down_revision: str | None = "e7f8a9b0c2d3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "website_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("visitor_hash", sa.String(64), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("utm_source", sa.String(120), nullable=True),
        sa.Column("utm_medium", sa.String(120), nullable=True),
        sa.Column("utm_campaign", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_date_berlin", sa.Date(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "event_type IN ('page_view','telegram_cta_click')",
            name="ck_website_events_event_type",
        ),
    )
    op.create_index("idx_website_events_created_at", "website_events", ["created_at"])
    op.create_index(
        "idx_website_events_local_date_type",
        "website_events",
        ["local_date_berlin", "event_type"],
    )
    op.create_index(
        "idx_website_events_visitor_date",
        "website_events",
        ["visitor_hash", "local_date_berlin"],
    )
    op.create_index(
        "idx_website_events_path_date",
        "website_events",
        ["path", "local_date_berlin"],
    )


def downgrade() -> None:
    op.drop_index("idx_website_events_path_date", table_name="website_events")
    op.drop_index("idx_website_events_visitor_date", table_name="website_events")
    op.drop_index("idx_website_events_local_date_type", table_name="website_events")
    op.drop_index("idx_website_events_created_at", table_name="website_events")
    op.drop_table("website_events")
