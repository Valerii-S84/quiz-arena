"""m28_daily_push_log_and_completed_index

Revision ID: ab12cd34ef56
Revises: f9e8d7c6b5a4
Create Date: 2026-02-26 16:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ab12cd34ef56"
down_revision: str | None = "f9e8d7c6b5a4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_push_logs",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("berlin_date", sa.Date(), nullable=False),
        sa.Column("push_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id", "berlin_date"),
    )
    op.create_index(
        "idx_daily_push_logs_berlin_date",
        "daily_push_logs",
        ["berlin_date"],
        unique=False,
    )

    op.drop_index("uq_daily_runs_user_date", table_name="daily_runs")
    op.create_index(
        "uq_daily_runs_user_date_completed",
        "daily_runs",
        ["user_id", "berlin_date"],
        unique=True,
        postgresql_where=sa.text("status = 'COMPLETED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_daily_runs_user_date_completed", table_name="daily_runs")
    op.create_index(
        "uq_daily_runs_user_date",
        "daily_runs",
        ["user_id", "berlin_date"],
        unique=True,
    )

    op.drop_index("idx_daily_push_logs_berlin_date", table_name="daily_push_logs")
    op.drop_table("daily_push_logs")
