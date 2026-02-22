"""m20_add_dismissed_at_to_offers_impressions

Revision ID: cd45ef678901
Revises: bc34de56f789
Create Date: 2026-02-22 17:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cd45ef678901"
down_revision: str | None = "bc34de56f789"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "offers_impressions",
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE offers_impressions
        SET dismissed_at = clicked_at
        WHERE dismiss_reason IS NOT NULL
          AND dismissed_at IS NULL
          AND clicked_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("offers_impressions", "dismissed_at")
