"""m27_daily_challenge_v2

Revision ID: f9e8d7c6b5a4
Revises: f1a2b3c4d5e7
Create Date: 2026-02-26 12:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f9e8d7c6b5a4"
down_revision: str | None = "f1a2b3c4d5e7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_daily_challenge_user_date", table_name="quiz_sessions")

    op.create_table(
        "daily_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("berlin_date", sa.Date(), nullable=False),
        sa.Column(
            "current_question",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "score",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('IN_PROGRESS','COMPLETED','ABANDONED')",
            name="ck_daily_runs_status",
        ),
        sa.CheckConstraint(
            "current_question >= 0 AND current_question <= 7",
            name="ck_daily_runs_question_range",
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= current_question AND score <= 7",
            name="ck_daily_runs_score_range",
        ),
        sa.CheckConstraint(
            "(status != 'COMPLETED') OR completed_at IS NOT NULL",
            name="ck_daily_runs_completed_at_required",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_daily_runs_user_date", "daily_runs", ["user_id", "berlin_date"], unique=True)
    op.create_index(
        "idx_daily_runs_berlin_date_status",
        "daily_runs",
        ["berlin_date", "status"],
        unique=False,
    )

    op.create_table(
        "daily_question_sets",
        sa.Column("berlin_date", sa.Date(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "position >= 1 AND position <= 7",
            name="ck_daily_question_sets_position_range",
        ),
        sa.PrimaryKeyConstraint("berlin_date", "position"),
    )
    op.create_index(
        "idx_daily_question_sets_question_id",
        "daily_question_sets",
        ["question_id"],
        unique=False,
    )

    op.add_column(
        "quiz_sessions",
        sa.Column("daily_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_quiz_sessions_daily_run_id_daily_runs",
        "quiz_sessions",
        "daily_runs",
        ["daily_run_id"],
        ["id"],
    )
    op.create_index("idx_sessions_daily_run", "quiz_sessions", ["daily_run_id"], unique=False)
    op.create_index(
        "uq_daily_run_single_started_session",
        "quiz_sessions",
        ["daily_run_id"],
        unique=True,
        postgresql_where=sa.text(
            "source = 'DAILY_CHALLENGE' AND status = 'STARTED' AND daily_run_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_daily_run_single_started_session", table_name="quiz_sessions")
    op.drop_index("idx_sessions_daily_run", table_name="quiz_sessions")
    op.drop_constraint(
        "fk_quiz_sessions_daily_run_id_daily_runs",
        "quiz_sessions",
        type_="foreignkey",
    )
    op.drop_column("quiz_sessions", "daily_run_id")

    op.drop_index("idx_daily_question_sets_question_id", table_name="daily_question_sets")
    op.drop_table("daily_question_sets")

    op.drop_index("idx_daily_runs_berlin_date_status", table_name="daily_runs")
    op.drop_index("uq_daily_runs_user_date", table_name="daily_runs")
    op.drop_table("daily_runs")

    op.create_index(
        "uq_daily_challenge_user_date",
        "quiz_sessions",
        ["user_id", "local_date_berlin"],
        unique=True,
        postgresql_where=sa.text("source = 'DAILY_CHALLENGE'"),
    )
