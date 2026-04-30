"""m47_open_arena_foundation

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-04-30 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "arena_duels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("creator_user_id", sa.BigInteger(), nullable=False),
        sa.Column("baseline_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "question_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("mode_code", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_friend_challenge_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('DRAFT','ACTIVE','EXPIRED','CANCELLED')",
            name="ck_arena_duels_status",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(question_ids) = 'array' AND jsonb_array_length(question_ids) = 7",
            name="ck_arena_duels_question_ids_7",
        ),
        sa.ForeignKeyConstraint(["creator_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_friend_challenge_id"], ["friend_challenges.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_arena_duels_creator_created",
        "arena_duels",
        ["creator_user_id", "created_at"],
    )
    op.create_index(
        "idx_arena_duels_status_expires_created",
        "arena_duels",
        ["status", "expires_at", "created_at"],
    )
    op.create_index(
        "idx_arena_duels_source_friend",
        "arena_duels",
        ["source_friend_challenge_id"],
    )

    op.create_table(
        "arena_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("arena_duel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("time_ms", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('CREATOR_BASELINE','CHALLENGER')",
            name="ck_arena_attempts_role",
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 7)",
            name="ck_arena_attempts_score_range",
        ),
        sa.CheckConstraint(
            "time_ms IS NULL OR time_ms >= 0",
            name="ck_arena_attempts_time_ms_non_negative",
        ),
        sa.ForeignKeyConstraint(["arena_duel_id"], ["arena_duels.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_arena_attempts_duel", "arena_attempts", ["arena_duel_id"])
    op.create_index("idx_arena_attempts_user", "arena_attempts", ["user_id"])
    op.create_index(
        "uq_arena_attempts_duel_user",
        "arena_attempts",
        ["arena_duel_id", "user_id"],
        unique=True,
    )
    op.create_unique_constraint(
        "uq_arena_attempts_duel_id_id",
        "arena_attempts",
        ["arena_duel_id", "id"],
    )
    op.create_foreign_key(
        "fk_arena_duels_baseline_attempt_id_arena_attempts",
        "arena_duels",
        "arena_attempts",
        ["id", "baseline_attempt_id"],
        ["arena_duel_id", "id"],
    )

    op.add_column(
        "quiz_sessions",
        sa.Column("arena_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("quiz_sessions", sa.Column("arena_round", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_quiz_sessions_arena_attempt_id",
        "quiz_sessions",
        "arena_attempts",
        ["arena_attempt_id"],
        ["id"],
    )
    op.drop_constraint("ck_quiz_sessions_source", "quiz_sessions", type_="check")
    op.create_check_constraint(
        "ck_quiz_sessions_source",
        "quiz_sessions",
        "source IN ('MENU','DAILY_CHALLENGE','FRIEND_CHALLENGE','TOURNAMENT','ARENA_DUEL')",
    )
    op.create_check_constraint(
        "ck_quiz_sessions_arena_source_link",
        "quiz_sessions",
        "((source = 'ARENA_DUEL' AND arena_attempt_id IS NOT NULL "
        "AND arena_round IS NOT NULL) OR (source != 'ARENA_DUEL' "
        "AND arena_attempt_id IS NULL AND arena_round IS NULL))",
    )
    op.create_check_constraint(
        "ck_quiz_sessions_arena_round_consistency",
        "quiz_sessions",
        "(arena_round IS NULL) OR (arena_round >= 1 AND arena_round <= 7)",
    )
    op.create_index(
        "idx_sessions_arena_attempt",
        "quiz_sessions",
        ["arena_attempt_id", "arena_round"],
    )
    op.create_index(
        "uq_sessions_arena_attempt_round",
        "quiz_sessions",
        ["arena_attempt_id", "arena_round"],
        unique=True,
        postgresql_where=sa.text("arena_attempt_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_sessions_arena_attempt_round", table_name="quiz_sessions")
    op.drop_index("idx_sessions_arena_attempt", table_name="quiz_sessions")
    op.drop_constraint("ck_quiz_sessions_arena_round_consistency", "quiz_sessions", type_="check")
    op.drop_constraint("ck_quiz_sessions_arena_source_link", "quiz_sessions", type_="check")
    op.drop_constraint("ck_quiz_sessions_source", "quiz_sessions", type_="check")
    op.execute(
        sa.text(
            "DELETE FROM quiz_attempts "
            "WHERE session_id IN (SELECT id FROM quiz_sessions WHERE source = 'ARENA_DUEL')"
        )
    )
    op.execute(sa.text("DELETE FROM quiz_sessions WHERE source = 'ARENA_DUEL'"))
    op.create_check_constraint(
        "ck_quiz_sessions_source",
        "quiz_sessions",
        "source IN ('MENU','DAILY_CHALLENGE','FRIEND_CHALLENGE','TOURNAMENT')",
    )
    op.drop_constraint("fk_quiz_sessions_arena_attempt_id", "quiz_sessions", type_="foreignkey")
    op.drop_column("quiz_sessions", "arena_round")
    op.drop_column("quiz_sessions", "arena_attempt_id")

    op.drop_constraint(
        "fk_arena_duels_baseline_attempt_id_arena_attempts",
        "arena_duels",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_arena_attempts_duel_id_id",
        "arena_attempts",
        type_="unique",
    )
    op.drop_index("uq_arena_attempts_duel_user", table_name="arena_attempts")
    op.drop_index("idx_arena_attempts_user", table_name="arena_attempts")
    op.drop_index("idx_arena_attempts_duel", table_name="arena_attempts")
    op.drop_table("arena_attempts")

    op.drop_index("idx_arena_duels_source_friend", table_name="arena_duels")
    op.drop_index("idx_arena_duels_status_expires_created", table_name="arena_duels")
    op.drop_index("idx_arena_duels_creator_created", table_name="arena_duels")
    op.drop_table("arena_duels")
