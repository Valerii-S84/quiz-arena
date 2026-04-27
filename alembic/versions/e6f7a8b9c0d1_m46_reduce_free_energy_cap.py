"""m46_reduce_free_energy_cap

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-04-27 15:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE energy_state SET free_energy = 10 WHERE free_energy > 10")
    op.execute("UPDATE energy_state SET free_cap = 10 WHERE free_cap > 10")
    op.alter_column(
        "energy_state",
        "free_cap",
        server_default=sa.text("10"),
        existing_type=sa.SmallInteger(),
        existing_nullable=False,
    )
    op.drop_constraint(
        "ck_energy_state_free_energy_range",
        "energy_state",
        type_="check",
    )
    op.create_check_constraint(
        "ck_energy_state_free_energy_range",
        "energy_state",
        "free_energy >= 0 AND free_energy <= 10",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_energy_state_free_energy_range",
        "energy_state",
        type_="check",
    )
    op.create_check_constraint(
        "ck_energy_state_free_energy_range",
        "energy_state",
        "free_energy >= 0 AND free_energy <= 20",
    )
    op.alter_column(
        "energy_state",
        "free_cap",
        server_default=sa.text("20"),
        existing_type=sa.SmallInteger(),
        existing_nullable=False,
    )
