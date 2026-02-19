"""m12_friend_challenges_and_session_link

Revision ID: b3c4d5e6f7a8
Revises: a7b8c9d0e1f2
Create Date: 2026-02-19 19:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "friend_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invite_token", sa.String(length=32), nullable=False),
        sa.Column("creator_user_id", sa.BigInteger(), nullable=False),
        sa.Column("opponent_user_id", sa.BigInteger(), nullable=True),
        sa.Column("mode_code", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_round", sa.Integer(), nullable=False),
        sa.Column("total_rounds", sa.Integer(), nullable=False),
        sa.Column("creator_score", sa.Integer(), nullable=False),
        sa.Column("opponent_score", sa.Integer(), nullable=False),
        sa.Column("creator_answered_round", sa.Integer(), nullable=False),
        sa.Column("opponent_answered_round", sa.Integer(), nullable=False),
        sa.Column("winner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('ACTIVE','COMPLETED','CANCELED')",
            name="ck_friend_challenges_status",
        ),
        sa.CheckConstraint("current_round >= 1", name="ck_friend_challenges_current_round_positive"),
        sa.CheckConstraint("total_rounds >= 1", name="ck_friend_challenges_total_rounds_positive"),
        sa.CheckConstraint("creator_score >= 0", name="ck_friend_challenges_creator_score_non_negative"),
        sa.CheckConstraint("opponent_score >= 0", name="ck_friend_challenges_opponent_score_non_negative"),
        sa.CheckConstraint(
            "creator_answered_round >= 0",
            name="ck_friend_challenges_creator_answered_non_negative",
        ),
        sa.CheckConstraint(
            "opponent_answered_round >= 0",
            name="ck_friend_challenges_opponent_answered_non_negative",
        ),
        sa.ForeignKeyConstraint(["creator_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["opponent_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["winner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_token"),
    )
    op.create_index(
        "idx_friend_challenges_creator_created",
        "friend_challenges",
        ["creator_user_id", "created_at"],
    )
    op.create_index(
        "idx_friend_challenges_opponent_created",
        "friend_challenges",
        ["opponent_user_id", "created_at"],
    )
    op.create_index(
        "idx_friend_challenges_status_created",
        "friend_challenges",
        ["status", "created_at"],
    )

    op.add_column("quiz_sessions", sa.Column("friend_challenge_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("quiz_sessions", sa.Column("friend_challenge_round", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_quiz_sessions_friend_challenge_id",
        "quiz_sessions",
        "friend_challenges",
        ["friend_challenge_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_quiz_sessions_friend_source_link",
        "quiz_sessions",
        "(source != 'FRIEND_CHALLENGE') OR friend_challenge_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_quiz_sessions_friend_round_consistency",
        "quiz_sessions",
        "(friend_challenge_id IS NULL AND friend_challenge_round IS NULL) "
        "OR (friend_challenge_id IS NOT NULL AND friend_challenge_round >= 1)",
    )
    op.create_index(
        "idx_sessions_friend_challenge",
        "quiz_sessions",
        ["friend_challenge_id", "friend_challenge_round"],
    )
    op.create_index(
        "uq_sessions_friend_challenge_user_round",
        "quiz_sessions",
        ["friend_challenge_id", "user_id", "friend_challenge_round"],
        unique=True,
        postgresql_where=sa.text("friend_challenge_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_sessions_friend_challenge_user_round", table_name="quiz_sessions")
    op.drop_index("idx_sessions_friend_challenge", table_name="quiz_sessions")
    op.drop_constraint("ck_quiz_sessions_friend_round_consistency", "quiz_sessions", type_="check")
    op.drop_constraint("ck_quiz_sessions_friend_source_link", "quiz_sessions", type_="check")
    op.drop_constraint("fk_quiz_sessions_friend_challenge_id", "quiz_sessions", type_="foreignkey")
    op.drop_column("quiz_sessions", "friend_challenge_round")
    op.drop_column("quiz_sessions", "friend_challenge_id")

    op.drop_index("idx_friend_challenges_status_created", table_name="friend_challenges")
    op.drop_index("idx_friend_challenges_opponent_created", table_name="friend_challenges")
    op.drop_index("idx_friend_challenges_creator_created", table_name="friend_challenges")
    op.drop_table("friend_challenges")
