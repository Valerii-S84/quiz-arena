"""m41_drop_legacy_admin_promo_tables

Revision ID: e5f6a7b8c9da
Revises: d1e2f3a4b5c6
Create Date: 2026-03-08 18:20:00.000000
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9da"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

admins = sa.table(
    "admins",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("email", sa.String()),
    sa.column("role", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)

promo_audit_log = sa.table(
    "promo_audit_log",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("admin_email", sa.String()),
    sa.column("admin_id", postgresql.UUID(as_uuid=True)),
)


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('admin','super_admin')", name="ck_admins_role"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_admins_email", "admins", ["email"], unique=True)

    op.add_column(
        "promo_audit_log",
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_promo_audit_log_admin_id_admins",
        "promo_audit_log",
        "admins",
        ["admin_id"],
        ["id"],
    )

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        now_utc = datetime.now(timezone.utc)
        email_to_id: dict[str, object] = {}
        rows = session.execute(select(promo_audit_log.c.admin_email).distinct()).scalars().all()
        for raw_email in rows:
            if raw_email is None:
                continue
            email = str(raw_email).strip().lower()
            if not email or email in email_to_id:
                continue
            admin_id = uuid4()
            email_to_id[email] = admin_id
            session.execute(
                admins.insert().values(
                    id=admin_id,
                    email=email,
                    role="admin",
                    created_at=now_utc,
                    updated_at=now_utc,
                )
            )
            session.execute(
                promo_audit_log.update()
                .where(sa.func.lower(promo_audit_log.c.admin_email) == email)
                .values(admin_id=admin_id)
            )
        session.flush()
    finally:
        session.close()

    op.alter_column("promo_audit_log", "admin_id", nullable=False)
    op.drop_column("promo_audit_log", "admin_email")

    op.execute("DROP TABLE IF EXISTS admin_promo_code_usages CASCADE")
    op.execute("DROP TABLE IF EXISTS admin_promo_codes CASCADE")


def downgrade() -> None:
    op.add_column("promo_audit_log", sa.Column("admin_email", sa.String(length=100), nullable=True))
    op.execute(
        """
        UPDATE promo_audit_log
        SET admin_email = admins.email
        FROM admins
        WHERE admins.id = promo_audit_log.admin_id
        """
    )
    op.alter_column("promo_audit_log", "admin_email", nullable=False)
    op.drop_constraint("fk_promo_audit_log_admin_id_admins", "promo_audit_log", type_="foreignkey")
    op.drop_column("promo_audit_log", "admin_id")

    op.create_table(
        "admin_promo_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("promo_type", sa.String(30), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("product_code", sa.String(32), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("uses_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channel_tag", sa.String(50), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "promo_type IN ('discount_percent','discount_stars','bonus_energy','bonus_subscription_days','free_product')",
            name="ck_admin_promo_codes_type",
        ),
        sa.CheckConstraint(
            "status IN ('active','paused','expired','archived')",
            name="ck_admin_promo_codes_status",
        ),
        sa.CheckConstraint("value >= 0", name="ck_admin_promo_codes_value_non_negative"),
        sa.CheckConstraint("max_uses >= 0", name="ck_admin_promo_codes_max_uses_non_negative"),
        sa.CheckConstraint("uses_count >= 0", name="ck_admin_promo_codes_uses_non_negative"),
        sa.UniqueConstraint("code", name="uq_admin_promo_codes_code"),
    )

    op.create_table(
        "admin_promo_code_usages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("promo_code_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["promo_code_id"],
            ["admin_promo_codes.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_admin_promo_code_usages_code",
        "admin_promo_code_usages",
        ["promo_code_id"],
    )
    op.create_index(
        "idx_admin_promo_code_usages_user_used",
        "admin_promo_code_usages",
        ["user_id", "used_at"],
    )

    op.drop_index("uq_admins_email", table_name="admins")
    op.drop_table("admins")
