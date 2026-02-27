"""m30_channel_bonus_claim_timestamp

Revision ID: c8d9e0f1a2b3
Revises: bf34ce78a901
Create Date: 2026-02-26 21:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "bf34ce78a901"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("channel_bonus_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "channel_bonus_claimed_at")
