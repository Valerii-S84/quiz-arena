"""m18_add_processing_task_id_to_processed_updates

Revision ID: aa12bb34cc56
Revises: e1f2a3b4c5d6
Create Date: 2026-02-22 14:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "aa12bb34cc56"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "processed_updates",
        sa.Column("processing_task_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "idx_processed_updates_processing_status_age",
        "processed_updates",
        ["processed_at"],
        unique=False,
        postgresql_where=sa.text("status = 'PROCESSING'"),
    )


def downgrade() -> None:
    op.drop_index("idx_processed_updates_processing_status_age", table_name="processed_updates")
    op.drop_column("processed_updates", "processing_task_id")
