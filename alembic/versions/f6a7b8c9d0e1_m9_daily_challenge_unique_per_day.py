"""m9_daily_challenge_unique_per_day

Revision ID: f6a7b8c9d0e1
Revises: e4f5a6b7c8d9
Create Date: 2026-02-18 16:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_daily_challenge_user_date",
        "quiz_sessions",
        ["user_id", "local_date_berlin"],
        unique=True,
        postgresql_where=sa.text("source = 'DAILY_CHALLENGE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_daily_challenge_user_date", table_name="quiz_sessions")
