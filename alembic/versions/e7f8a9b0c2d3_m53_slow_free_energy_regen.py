"""m53_slow_free_energy_regen

Revision ID: e7f8a9b0c2d3
Revises: d6e7f8a9b0c2
Create Date: 2026-06-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7f8a9b0c2d3"
down_revision: str | None = "d6e7f8a9b0c2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "energy_state",
        "regen_interval_sec",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("10800"),
    )
    op.execute("UPDATE energy_state SET regen_interval_sec = 10800 WHERE regen_interval_sec = 1800")


def downgrade() -> None:
    op.execute("UPDATE energy_state SET regen_interval_sec = 1800 WHERE regen_interval_sec = 10800")
    op.alter_column(
        "energy_state",
        "regen_interval_sec",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("1800"),
    )
