"""m32_private_tournaments_foundation

Revision ID: e2f3a4b5c6d7
Revises: d9e0f1a2b3c4
Create Date: 2026-02-28 00:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "d9e0f1a2b3c4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tournaments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("max_participants", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("current_round", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("registration_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("round_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invite_code", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "type IN ('PRIVATE','DAILY_ARENA')",
            name="ck_tournaments_type",
        ),
        sa.CheckConstraint(
            "status IN ('REGISTRATION','ROUND_1','ROUND_2','ROUND_3','COMPLETED','CANCELED')",
            name="ck_tournaments_status",
        ),
        sa.CheckConstraint(
            "format IN ('QUICK_5','QUICK_12')",
            name="ck_tournaments_format",
        ),
        sa.CheckConstraint(
            "max_participants >= 2 AND max_participants <= 8",
            name="ck_tournaments_max_participants_range",
        ),
        sa.CheckConstraint(
            "current_round >= 0 AND current_round <= 3",
            name="ck_tournaments_current_round_range",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_code", name="uq_tournaments_invite_code"),
    )
    op.create_index(
        "idx_tournaments_status_registration_deadline",
        "tournaments",
        ["status", "registration_deadline"],
    )
    op.create_index(
        "idx_tournaments_status_round_deadline",
        "tournaments",
        ["status", "round_deadline"],
    )

    op.create_table(
        "tournament_participants",
        sa.Column("tournament_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("tie_break", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "score >= 0",
            name="ck_tournament_participants_score_non_negative",
        ),
        sa.CheckConstraint(
            "tie_break >= 0",
            name="ck_tournament_participants_tie_break_non_negative",
        ),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("tournament_id", "user_id"),
    )
    op.create_index(
        "idx_tournament_participants_tournament_score",
        "tournament_participants",
        ["tournament_id", "score", "tie_break"],
    )

    op.create_table(
        "tournament_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tournament_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("user_a", sa.BigInteger(), nullable=False),
        sa.Column("user_b", sa.BigInteger(), nullable=True),
        sa.Column("friend_challenge_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("winner_id", sa.BigInteger(), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "round_no >= 1 AND round_no <= 3",
            name="ck_tournament_matches_round_no_range",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','COMPLETED','WALKOVER')",
            name="ck_tournament_matches_status",
        ),
        sa.CheckConstraint(
            "user_b IS NULL OR user_a <> user_b",
            name="ck_tournament_matches_no_self_pair",
        ),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"]),
        sa.ForeignKeyConstraint(["user_a"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_b"], ["users.id"]),
        sa.ForeignKeyConstraint(["friend_challenge_id"], ["friend_challenges.id"]),
        sa.ForeignKeyConstraint(["winner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("friend_challenge_id", name="uq_tournament_matches_friend_challenge"),
    )
    op.create_index(
        "idx_tournament_matches_tournament_round_status",
        "tournament_matches",
        ["tournament_id", "round_no", "status"],
    )
    op.create_index(
        "idx_tournament_matches_tournament_status_deadline",
        "tournament_matches",
        ["tournament_id", "status", "deadline"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_tournament_matches_tournament_status_deadline",
        table_name="tournament_matches",
    )
    op.drop_index(
        "idx_tournament_matches_tournament_round_status",
        table_name="tournament_matches",
    )
    op.drop_table("tournament_matches")

    op.drop_index(
        "idx_tournament_participants_tournament_score",
        table_name="tournament_participants",
    )
    op.drop_table("tournament_participants")

    op.drop_index("idx_tournaments_status_round_deadline", table_name="tournaments")
    op.drop_index(
        "idx_tournaments_status_registration_deadline",
        table_name="tournaments",
    )
    op.drop_table("tournaments")
