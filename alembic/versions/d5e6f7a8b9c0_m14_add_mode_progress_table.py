"""m14_add_mode_progress_table

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-02-19 22:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mode_progress",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("mode_code", sa.String(length=32), nullable=False),
        sa.Column("preferred_level", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "preferred_level IN ('A1','A2','B1','B2','C1','C2')",
            name="ck_mode_progress_preferred_level",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id", "mode_code"),
    )
    op.create_index("idx_mode_progress_mode", "mode_progress", ["mode_code"])


def downgrade() -> None:
    op.drop_index("idx_mode_progress_mode", table_name="mode_progress")
    op.drop_table("mode_progress")
