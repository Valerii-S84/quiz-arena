"""m42_daily_cup_round_scores

Revision ID: a1b2c3d4e5f6
Revises: e5f6a7b8c9da
Create Date: 2026-03-08 22:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "e5f6a7b8c9da"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tournaments") as batch_op:
        batch_op.drop_constraint("ck_tournaments_status", type_="check")
        batch_op.create_check_constraint(
            "ck_tournaments_status",
            (
                "status IN ("
                "'REGISTRATION','ROUND_1','ROUND_2','ROUND_3','ROUND_4','BRACKET_LIVE',"
                "'COMPLETED','CANCELED'"
                ")"
            ),
        )

    op.create_table(
        "tournament_round_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tournament_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("opponent_id", sa.BigInteger(), nullable=True),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("is_draw", sa.Boolean(), nullable=False),
        sa.Column("correct_answers", sa.Integer(), nullable=False),
        sa.Column("total_time_ms", sa.Integer(), nullable=False),
        sa.Column("got_bye", sa.Boolean(), nullable=False),
        sa.Column("auto_finished", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opponent_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["player_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("round_number >= 1 AND round_number <= 4", name="ck_round_scores_round_range"),
        sa.CheckConstraint("wins IN (0, 1, 2)", name="ck_round_scores_points_range"),
        sa.CheckConstraint(
            "correct_answers >= 0 AND correct_answers <= 7",
            name="ck_round_scores_correct_answers_range",
        ),
        sa.CheckConstraint("total_time_ms >= 0", name="ck_round_scores_total_time_non_negative"),
    )
    op.create_index(
        "uq_round_scores_tournament_round_player",
        "tournament_round_scores",
        ["tournament_id", "round_number", "player_id"],
        unique=True,
    )
    op.create_index(
        "idx_round_scores_tournament_player",
        "tournament_round_scores",
        ["tournament_id", "player_id", "round_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_round_scores_tournament_player", table_name="tournament_round_scores")
    op.drop_index("uq_round_scores_tournament_round_player", table_name="tournament_round_scores")
    op.drop_table("tournament_round_scores")

    with op.batch_alter_table("tournaments") as batch_op:
        batch_op.drop_constraint("ck_tournaments_status", type_="check")
        batch_op.create_check_constraint(
            "ck_tournaments_status",
            (
                "status IN ("
                "'REGISTRATION','ROUND_1','ROUND_2','ROUND_3','BRACKET_LIVE',"
                "'COMPLETED','CANCELED'"
                ")"
            ),
        )
