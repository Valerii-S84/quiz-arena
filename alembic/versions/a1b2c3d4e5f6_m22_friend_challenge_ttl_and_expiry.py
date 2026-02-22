"""m22_friend_challenge_ttl_and_expiry

Revision ID: a1b2c3d4e5f6
Revises: de56fa78bc90
Create Date: 2026-02-22 23:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "de56fa78bc90"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "friend_challenges",
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '24 hours'"),
        ),
    )
    op.alter_column("friend_challenges", "expires_at", server_default=None)
    op.add_column(
        "friend_challenges",
        sa.Column("expires_last_chance_notified_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.drop_constraint("ck_friend_challenges_status", "friend_challenges", type_="check")
    op.create_check_constraint(
        "ck_friend_challenges_status",
        "friend_challenges",
        "status IN ('ACTIVE','COMPLETED','CANCELED','EXPIRED')",
    )

    op.create_index(
        "idx_friend_challenges_status_expires",
        "friend_challenges",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_friend_challenges_status_expires", table_name="friend_challenges")

    op.drop_constraint("ck_friend_challenges_status", "friend_challenges", type_="check")
    op.create_check_constraint(
        "ck_friend_challenges_status",
        "friend_challenges",
        "status IN ('ACTIVE','COMPLETED','CANCELED')",
    )

    op.drop_column("friend_challenges", "expires_last_chance_notified_at")
    op.drop_column("friend_challenges", "expires_at")
