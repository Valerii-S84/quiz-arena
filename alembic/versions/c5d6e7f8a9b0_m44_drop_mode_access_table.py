"""m44_drop_mode_access_table

Revision ID: c5d6e7f8a9b0
Revises: b7c8d9e0f1a2, f3b4c5d6e7f8
Create Date: 2026-03-14 21:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: tuple[str, str] = ("b7c8d9e0f1a2", "f3b4c5d6e7f8")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("mode_access")


def downgrade() -> None:
    op.create_table(
        "mode_access",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("mode_code", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_purchase_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('FREE','MEGA_PACK','PREMIUM')",
            name="ck_mode_access_source",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','EXPIRED','REVOKED')",
            name="ck_mode_access_status",
        ),
        sa.ForeignKeyConstraint(["source_purchase_id"], ["purchases.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_mode_access_idempotency_key"),
        sa.UniqueConstraint(
            "user_id",
            "mode_code",
            "source",
            "starts_at",
            name="uq_mode_access_user_mode_source_starts",
        ),
    )
    op.create_index("idx_mode_access_user_mode", "mode_access", ["user_id", "mode_code"])
    op.create_index("idx_mode_access_mode", "mode_access", ["mode_code"])
    op.create_index("idx_mode_access_ends", "mode_access", ["ends_at"])
