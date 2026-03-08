"""m39_sync_legacy_admin_promo_codes

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-03-08 13:15:00.000000
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.promo_codes import hash_promo_code, normalize_promo_code
from app.services.promo_encryption import encrypt_promo_code

# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b6c7d8e9f0a1"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

OPEN_ENDED_VALID_UNTIL = datetime(9999, 12, 31, tzinfo=timezone.utc)
LEGACY_TO_RUNTIME_TYPE = {
    "discount_percent": "PERCENT_DISCOUNT",
    "bonus_subscription_days": "PREMIUM_GRANT",
}
LEGACY_TO_RUNTIME_STATUS = {
    "active": "ACTIVE",
    "paused": "PAUSED",
    "expired": "EXPIRED",
    "archived": "EXPIRED",
}

legacy_admin_promo_codes = sa.table(
    "admin_promo_codes",
    sa.column("id", sa.String()),
    sa.column("code", sa.String()),
    sa.column("promo_type", sa.String()),
    sa.column("value", sa.Numeric()),
    sa.column("product_code", sa.String()),
    sa.column("max_uses", sa.Integer()),
    sa.column("uses_count", sa.Integer()),
    sa.column("valid_from", sa.DateTime(timezone=True)),
    sa.column("valid_until", sa.DateTime(timezone=True)),
    sa.column("channel_tag", sa.String()),
    sa.column("status", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)

runtime_promo_codes = sa.table(
    "promo_codes",
    sa.column("id", sa.BigInteger()),
    sa.column("code_hash", sa.String()),
    sa.column("code_prefix", sa.String()),
    sa.column("code_encrypted", sa.LargeBinary()),
    sa.column("campaign_name", sa.String()),
    sa.column("promo_type", sa.String()),
    sa.column("grant_premium_days", sa.SmallInteger()),
    sa.column("discount_percent", sa.SmallInteger()),
    sa.column("target_scope", sa.String()),
    sa.column("status", sa.String()),
    sa.column("valid_from", sa.DateTime(timezone=True)),
    sa.column("valid_until", sa.DateTime(timezone=True)),
    sa.column("max_total_uses", sa.Integer()),
    sa.column("used_total", sa.Integer()),
    sa.column("max_uses_per_user", sa.SmallInteger()),
    sa.column("new_users_only", sa.Boolean()),
    sa.column("first_purchase_only", sa.Boolean()),
    sa.column("created_by", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)


def _resolve_discount_percent(value: Decimal) -> int | None:
    integer_value = int(value)
    if Decimal(integer_value) != value or not 1 <= integer_value <= 90:
        return None
    return integer_value


def _resolve_grant_days(value: Decimal) -> int | None:
    integer_value = int(value)
    if Decimal(integer_value) != value or integer_value not in {7, 30, 90}:
        return None
    return integer_value


def _resolve_campaign_name(*, channel_tag: str | None, raw_code: str) -> str:
    value = (channel_tag or "").strip()
    return value or raw_code


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        settings = get_settings()
        admin_rows = list(
            session.execute(
                select(legacy_admin_promo_codes).order_by(
                    legacy_admin_promo_codes.c.created_at.asc(),
                    legacy_admin_promo_codes.c.id.asc(),
                )
            ).mappings()
        )
        existing_hashes = set(session.execute(select(runtime_promo_codes.c.code_hash)).scalars().all())
        next_promo_id = (
            int(session.execute(select(func.coalesce(func.max(runtime_promo_codes.c.id), 0))).scalar_one() or 0)
            + 1
        )

        for legacy in admin_rows:
            runtime_type = LEGACY_TO_RUNTIME_TYPE.get(str(legacy["promo_type"]))
            runtime_status = LEGACY_TO_RUNTIME_STATUS.get(str(legacy["status"]))
            if runtime_type is None or runtime_status is None:
                continue

            raw_code = str(legacy["code"]).strip().upper()
            normalized_code = normalize_promo_code(raw_code)
            code_hash = hash_promo_code(
                normalized_code=normalized_code,
                pepper=settings.promo_secret_pepper,
            )
            if code_hash in existing_hashes:
                continue

            grant_days: int | None = None
            discount_percent: int | None = None
            raw_value = legacy["value"]
            if not isinstance(raw_value, Decimal):
                raw_value = Decimal(str(raw_value))
            if runtime_type == "PERCENT_DISCOUNT":
                discount_percent = _resolve_discount_percent(raw_value)
                if discount_percent is None:
                    continue
            else:
                grant_days = _resolve_grant_days(raw_value)
                if grant_days is None:
                    continue

            used_total = max(0, int(legacy["uses_count"]))
            max_uses = int(legacy["max_uses"])
            max_total_uses = None if max_uses == 0 else max(max_uses, used_total)
            target_scope = (
                "PREMIUM_ANY"
                if runtime_type == "PREMIUM_GRANT"
                else (str(legacy["product_code"]) if legacy["product_code"] else "ANY")
            )

            session.execute(
                runtime_promo_codes.insert().values(
                    id=next_promo_id,
                    code_hash=code_hash,
                    code_prefix=normalized_code[:8] or "PROMO",
                    code_encrypted=encrypt_promo_code(raw_code),
                    campaign_name=_resolve_campaign_name(
                        channel_tag=legacy["channel_tag"],
                        raw_code=raw_code,
                    ),
                    promo_type=runtime_type,
                    grant_premium_days=grant_days,
                    discount_percent=discount_percent,
                    target_scope=target_scope,
                    status=runtime_status,
                    valid_from=legacy["valid_from"],
                    valid_until=legacy["valid_until"] or OPEN_ENDED_VALID_UNTIL,
                    max_total_uses=max_total_uses,
                    used_total=used_total,
                    max_uses_per_user=1,
                    new_users_only=False,
                    first_purchase_only=False,
                    created_by="legacy_admin_promo_sync",
                    created_at=legacy["created_at"],
                    updated_at=legacy["updated_at"],
                )
            )
            existing_hashes.add(code_hash)
            next_promo_id += 1

        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    # Legacy promo sync is intentionally irreversible.
    return None
