"""m61_drop_channel_bonus_claimed_at

Revision ID: a0b1c2d3e4f6
Revises: f9a0b1c2d345
Create Date: 2026-09-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a0b1c2d3e4f6"
down_revision: str | None = "f9a0b1c2d345"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("users", "channel_bonus_claimed_at")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("channel_bonus_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
