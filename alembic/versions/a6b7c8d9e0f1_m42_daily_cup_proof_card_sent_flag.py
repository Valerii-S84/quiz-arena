"""m42_daily_cup_proof_card_sent_flag

Revision ID: a6b7c8d9e0f1
Revises: e5f6a7b8c9da
Create Date: 2026-03-09 11:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6b7c8d9e0f1"
down_revision: str | None = "e5f6a7b8c9da"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tournament_participants",
        sa.Column("proof_card_sent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tournament_participants", "proof_card_sent")
