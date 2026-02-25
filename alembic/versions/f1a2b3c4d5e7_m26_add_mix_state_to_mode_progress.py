"""m26_add_mix_state_to_mode_progress

Revision ID: f1a2b3c4d5e7
Revises: e7f8a9b0c1d2
Create Date: 2026-02-25 22:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e7"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mode_progress",
        sa.Column("mix_step", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "mode_progress",
        sa.Column("correct_in_mix", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("mode_progress", "correct_in_mix")
    op.drop_column("mode_progress", "mix_step")
