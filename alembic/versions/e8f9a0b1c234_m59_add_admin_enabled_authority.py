"""m59_add_admin_enabled_authority

Revision ID: e8f9a0b1c234
Revises: d7e8f9a0b123
Create Date: 2026-08-05 00:00:00.000000
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from alembic import op

revision: str = "e8f9a0b1c234"
down_revision: str | None = "d7e8f9a0b123"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

admins = sa.table(
    "admins",
    sa.column("id", sa.Uuid()),
    sa.column("email", sa.String()),
    sa.column("role", sa.String()),
    sa.column("enabled", sa.Boolean()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)


def _normalize_bootstrap_email(raw_email: object) -> str:
    email = str(raw_email or "").strip().lower()
    if not email or len(email) > 100:
        raise RuntimeError("Configured admin bootstrap email is invalid")
    return email


def _backfill_admin_authority(bind: Connection, *, bootstrap_email: str) -> None:
    email = _normalize_bootstrap_email(bootstrap_email)
    normalized_db_email = sa.func.lower(sa.func.trim(admins.c.email))
    matching_ids = list(
        bind.execute(sa.select(admins.c.id).where(normalized_db_email == email)).scalars().all()
    )
    if len(matching_ids) > 1:
        raise RuntimeError("Configured admin bootstrap identity is duplicated")

    total_rows = int(bind.execute(sa.select(sa.func.count()).select_from(admins)).scalar_one())
    bind.execute(admins.update().values(enabled=False))
    now_utc = datetime.now(timezone.utc)
    if not matching_ids:
        if total_rows:
            raise RuntimeError("Configured admin bootstrap identity is missing")
        bind.execute(
            admins.insert().values(
                id=uuid4(),
                email=email,
                role="admin",
                enabled=True,
                created_at=now_utc,
                updated_at=now_utc,
            )
        )
        return

    bind.execute(
        admins.update()
        .where(admins.c.id == matching_ids[0])
        .values(
            email=email,
            role="admin",
            enabled=True,
            updated_at=now_utc,
        )
    )


def upgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("Admin authority migration requires an online database connection")
    bootstrap_email = _normalize_bootstrap_email(
        op.get_context().config.attributes.get("admin_bootstrap_email")
    )
    op.add_column(
        "admins",
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    _backfill_admin_authority(op.get_bind(), bootstrap_email=bootstrap_email)


def downgrade() -> None:
    raise RuntimeError("Admin authority migration is security-critical and forward-only")
