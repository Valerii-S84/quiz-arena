"""m57_delivery_query_indexes

Revision ID: c7d8e9f0a1b3
Revises: b6c7d8e9f012
Create Date: 2026-07-13 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c7d8e9f0a1b3"
down_revision: str | None = "b6c7d8e9f012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_telegram_delivery_status_updated_at",
        "telegram_delivery_attempts",
        ["status", "updated_at"],
    )
    op.create_index(
        "idx_attempts_answered_at_user",
        "quiz_attempts",
        ["answered_at", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_attempts_answered_at_user", table_name="quiz_attempts")
    op.drop_index(
        "idx_telegram_delivery_status_updated_at",
        table_name="telegram_delivery_attempts",
    )
