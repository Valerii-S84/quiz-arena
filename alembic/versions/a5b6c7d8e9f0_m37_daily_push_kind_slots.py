"""m37_daily_push_kind_slots

Revision ID: a5b6c7d8e9f0
Revises: f2a1b3c4d5e6
Create Date: 2026-03-06 12:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a5b6c7d8e9f0"
down_revision: str | None = "f2a1b3c4d5e6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "daily_push_logs",
        sa.Column(
            "push_kind",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'MORNING'"),
        ),
    )
    op.create_check_constraint(
        "ck_daily_push_logs_push_kind",
        "daily_push_logs",
        "push_kind IN ('MORNING','EVENING_REMINDER')",
    )
    op.drop_constraint("daily_push_logs_pkey", "daily_push_logs", type_="primary")
    op.create_primary_key(
        "daily_push_logs_pkey",
        "daily_push_logs",
        ["user_id", "berlin_date", "push_kind"],
    )
    op.alter_column("daily_push_logs", "push_kind", server_default=None)


def downgrade() -> None:
    op.drop_constraint("daily_push_logs_pkey", "daily_push_logs", type_="primary")
    op.create_primary_key("daily_push_logs_pkey", "daily_push_logs", ["user_id", "berlin_date"])
    op.drop_constraint("ck_daily_push_logs_push_kind", "daily_push_logs", type_="check")
    op.drop_column("daily_push_logs", "push_kind")
