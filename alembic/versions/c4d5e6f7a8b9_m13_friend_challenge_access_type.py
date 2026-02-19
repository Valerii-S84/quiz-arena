"""m13_friend_challenge_access_type

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-02-19 21:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "friend_challenges",
        sa.Column(
            "access_type",
            sa.String(length=16),
            nullable=False,
            server_default="FREE",
        ),
    )
    op.create_check_constraint(
        "ck_friend_challenges_access_type",
        "friend_challenges",
        "access_type IN ('FREE','PAID_TICKET','PREMIUM')",
    )
    op.alter_column("friend_challenges", "access_type", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_friend_challenges_access_type", "friend_challenges", type_="check")
    op.drop_column("friend_challenges", "access_type")
