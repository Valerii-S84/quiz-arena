"""m23_friend_challenge_series_best_of

Revision ID: b2c3d4e5f607
Revises: a1b2c3d4e5f6
Create Date: 2026-02-23 01:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f607"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "friend_challenges",
        sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "friend_challenges",
        sa.Column("series_game_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("friend_challenges", "series_game_number", server_default=None)
    op.add_column(
        "friend_challenges",
        sa.Column("series_best_of", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("friend_challenges", "series_best_of", server_default=None)

    op.create_check_constraint(
        "ck_friend_challenges_series_game_positive",
        "friend_challenges",
        "series_game_number >= 1",
    )
    op.create_check_constraint(
        "ck_friend_challenges_series_best_of_positive",
        "friend_challenges",
        "series_best_of >= 1",
    )
    op.create_index(
        "idx_friend_challenges_series_game",
        "friend_challenges",
        ["series_id", "series_game_number"],
    )


def downgrade() -> None:
    op.drop_index("idx_friend_challenges_series_game", table_name="friend_challenges")
    op.drop_constraint("ck_friend_challenges_series_best_of_positive", "friend_challenges", type_="check")
    op.drop_constraint("ck_friend_challenges_series_game_positive", "friend_challenges", type_="check")
    op.drop_column("friend_challenges", "series_best_of")
    op.drop_column("friend_challenges", "series_game_number")
    op.drop_column("friend_challenges", "series_id")
