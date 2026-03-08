"""m38_add_encrypted_code_to_promo_codes

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-03-08 12:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b6c7d8e9f0a1"
down_revision: str | None = "a5b6c7d8e9f0"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "promo_codes",
        sa.Column("code_encrypted", postgresql.BYTEA(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("promo_codes", "code_encrypted")
