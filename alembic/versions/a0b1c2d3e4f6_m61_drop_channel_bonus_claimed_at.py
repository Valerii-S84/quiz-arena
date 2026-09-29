"""m61_retire_channel_bonus_claimed_at

Revision ID: a0b1c2d3e4f6
Revises: e8f9a0b1c234
Create Date: 2026-09-28 00:00:00.000000
"""

from collections.abc import Sequence

revision: str = "a0b1c2d3e4f6"
down_revision: str | None = "e8f9a0b1c234"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Keep the legacy column name while the immediately preceding runtime
    # remains a supported rollback target.
    pass


def downgrade() -> None:
    pass
