"""m29_referral_notifications_and_prompt_flag

Revision ID: bf34ce78a901
Revises: ab12cd34ef56
Create Date: 2026-02-26 17:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bf34ce78a901"
down_revision: str | None = "ab12cd34ef56"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("referrals", sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_referrals_notified_at", "referrals", ["notified_at"], unique=False)
    op.add_column(
        "users",
        sa.Column("referral_prompt_shown_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "referral_prompt_shown_at")
    op.drop_index("idx_referrals_notified_at", table_name="referrals")
    op.drop_column("referrals", "notified_at")
