"""m33_private_tournament_phase2_messages_proof

Revision ID: a3b4c5d6e7f8
Revises: e2f3a4b5c6d7
Create Date: 2026-02-28 01:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tournament_participants",
        sa.Column("standings_message_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "tournament_participants",
        sa.Column("proof_card_file_id", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tournament_participants", "proof_card_file_id")
    op.drop_column("tournament_participants", "standings_message_id")
