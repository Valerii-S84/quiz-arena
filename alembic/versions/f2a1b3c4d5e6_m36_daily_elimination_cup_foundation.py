"""m36_daily_elimination_cup_foundation

Revision ID: f2a1b3c4d5e6
Revises: c2d3e4f5a6b7
Create Date: 2026-03-04 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f2a1b3c4d5e6"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tournaments") as batch_op:
        batch_op.add_column(
            sa.Column("bracket", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
        )
        batch_op.alter_column(
            "type",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
        batch_op.drop_constraint("ck_tournaments_type", type_="check")
        batch_op.drop_constraint("ck_tournaments_status", type_="check")
        batch_op.drop_constraint("ck_tournaments_max_participants_range", type_="check")
        batch_op.drop_constraint("ck_tournaments_current_round_range", type_="check")
        batch_op.create_check_constraint(
            "ck_tournaments_type",
            "type IN ('PRIVATE','DAILY_ARENA','DAILY_ELIMINATION')",
        )
        batch_op.create_check_constraint(
            "ck_tournaments_status",
            (
                "status IN ("
                "'REGISTRATION','ROUND_1','ROUND_2','ROUND_3','BRACKET_LIVE',"
                "'COMPLETED','CANCELED'"
                ")"
            ),
        )
        batch_op.create_check_constraint(
            "ck_tournaments_max_participants_range",
            "max_participants >= 2 AND max_participants <= 2048",
        )
        batch_op.create_check_constraint(
            "ck_tournaments_current_round_range",
            "current_round >= 0 AND current_round <= 16",
        )

    with op.batch_alter_table("tournament_matches") as batch_op:
        batch_op.add_column(sa.Column("round_number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("bracket_slot_a", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("bracket_slot_b", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("match_timeout_task_id", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("player_a_finished_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("player_b_finished_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.drop_constraint("ck_tournament_matches_round_no_range", type_="check")
        batch_op.create_check_constraint(
            "ck_tournament_matches_round_no_range",
            "round_no >= 1 AND round_no <= 16",
        )


def downgrade() -> None:
    with op.batch_alter_table("tournament_matches") as batch_op:
        batch_op.drop_constraint("ck_tournament_matches_round_no_range", type_="check")
        batch_op.create_check_constraint(
            "ck_tournament_matches_round_no_range",
            "round_no >= 1 AND round_no <= 3",
        )
        batch_op.drop_column("player_b_finished_at")
        batch_op.drop_column("player_a_finished_at")
        batch_op.drop_column("match_timeout_task_id")
        batch_op.drop_column("bracket_slot_b")
        batch_op.drop_column("bracket_slot_a")
        batch_op.drop_column("round_number")

    with op.batch_alter_table("tournaments") as batch_op:
        batch_op.drop_constraint("ck_tournaments_current_round_range", type_="check")
        batch_op.drop_constraint("ck_tournaments_status", type_="check")
        batch_op.drop_constraint("ck_tournaments_type", type_="check")
        batch_op.drop_constraint("ck_tournaments_max_participants_range", type_="check")
        batch_op.create_check_constraint(
            "ck_tournaments_type",
            "type IN ('PRIVATE','DAILY_ARENA')",
        )
        batch_op.create_check_constraint(
            "ck_tournaments_status",
            "status IN ('REGISTRATION','ROUND_1','ROUND_2','ROUND_3','COMPLETED','CANCELED')",
        )
        batch_op.create_check_constraint(
            "ck_tournaments_max_participants_range",
            "max_participants >= 2 AND max_participants <= 8",
        )
        batch_op.create_check_constraint(
            "ck_tournaments_current_round_range",
            "current_round >= 0 AND current_round <= 3",
        )
        batch_op.alter_column(
            "type",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
            existing_nullable=False,
        )
        batch_op.drop_column("bracket")
