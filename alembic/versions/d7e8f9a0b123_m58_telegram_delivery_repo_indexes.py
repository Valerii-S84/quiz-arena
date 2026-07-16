"""m58_telegram_delivery_repo_indexes

Revision ID: d7e8f9a0b123
Revises: c6d7e8f9a012
Create Date: 2026-07-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7e8f9a0b123"
down_revision: str | None = "c6d7e8f9a012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        "idx_telegram_delivery_blocked_candidate",
        table_name="telegram_delivery_attempts",
    )
    op.create_index(
        "idx_telegram_delivery_blocked_candidate",
        "telegram_delivery_attempts",
        ["status", "is_blocked_candidate", "failed_at", "id"],
    )
    op.create_index(
        "idx_telegram_delivery_pending_claim",
        "telegram_delivery_attempts",
        ["flow", "created_at", "id", "attempt_count", "updated_at"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_telegram_delivery_pending_claim",
        table_name="telegram_delivery_attempts",
    )
    op.drop_index(
        "idx_telegram_delivery_blocked_candidate",
        table_name="telegram_delivery_attempts",
    )
    op.create_index(
        "idx_telegram_delivery_blocked_candidate",
        "telegram_delivery_attempts",
        ["is_blocked_candidate", "created_at"],
    )
