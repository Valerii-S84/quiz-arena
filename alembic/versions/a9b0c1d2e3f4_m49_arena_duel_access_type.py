"""m49_arena_duel_access_type

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-05-01 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: str | None = "f8a9b0c1d2e3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "arena_duels",
        sa.Column("access_type", sa.String(length=24), server_default="FREE", nullable=False),
    )
    op.add_column(
        "arena_attempts",
        sa.Column("access_type", sa.String(length=24), server_default="FREE", nullable=False),
    )
    op.create_check_constraint(
        "ck_arena_duels_access_type",
        "arena_duels",
        "access_type IN ('FREE','PAID_TICKET','PREMIUM')",
    )
    op.create_check_constraint(
        "ck_arena_attempts_access_type",
        "arena_attempts",
        "access_type IN ('FREE','PAID_TICKET','PREMIUM')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_arena_attempts_access_type", "arena_attempts", type_="check")
    op.drop_constraint("ck_arena_duels_access_type", "arena_duels", type_="check")
    op.drop_column("arena_attempts", "access_type")
    op.drop_column("arena_duels", "access_type")
