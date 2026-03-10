"""m42_add_round_start_time_to_tournaments

Revision ID: 0f1e2d3c4b5a
Revises: e5f6a7b8c9da
Create Date: 2026-03-10 13:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0f1e2d3c4b5a"
down_revision: str | None = "e5f6a7b8c9da"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column("round_start_time", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tournaments", "round_start_time")
