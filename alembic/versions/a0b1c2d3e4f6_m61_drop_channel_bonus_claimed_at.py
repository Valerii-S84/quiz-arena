"""m61_retire_channel_bonus_claimed_at

Revision ID: a0b1c2d3e4f6
Revises: e8f9a0b1c234
Create Date: 2026-09-28 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a0b1c2d3e4f6"
down_revision: str | None = "e8f9a0b1c234"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_LEGACY_COLUMN_NAME = "channel_bonus_claimed_at_legacy"


def upgrade() -> None:
    op.alter_column(
        "users",
        "channel_bonus_claimed_at",
        new_column_name=_LEGACY_COLUMN_NAME,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        _LEGACY_COLUMN_NAME,
        new_column_name="channel_bonus_claimed_at",
    )
