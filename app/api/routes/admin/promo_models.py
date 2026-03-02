from __future__ import annotations

import secrets
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.db.models.admin_promo_codes import AdminPromoCode

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class PromoCreateRequest(BaseModel):
    code: str = Field(min_length=4, max_length=50)
    type: str = Field(
        pattern="^(discount_percent|discount_stars|bonus_energy|bonus_subscription_days|free_product)$"
    )
    value: float = Field(ge=0)
    product_id: str | None = None
    max_uses: int = Field(default=0, ge=0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    channel_tag: str | None = Field(default=None, max_length=50)


class PromoBulkCreateRequest(BaseModel):
    prefix: str = Field(min_length=2, max_length=16)
    count: int = Field(ge=10, le=1000)
    type: str = Field(
        pattern="^(discount_percent|discount_stars|bonus_energy|bonus_subscription_days|free_product)$"
    )
    value: float = Field(ge=0)
    product_id: str | None = None
    max_uses: int = Field(default=0, ge=0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    channel_tag: str | None = Field(default=None, max_length=50)


class PromoPatchRequest(BaseModel):
    value: float | None = Field(default=None, ge=0)
    max_uses: int | None = Field(default=None, ge=0)
    valid_until: datetime | None = None
    channel_tag: str | None = Field(default=None, max_length=50)
    status: str | None = Field(default=None, pattern="^(active|paused|expired|archived)$")


def normalized_code(raw: str) -> str:
    return raw.strip().upper()


def generate_codes(*, prefix: str, count: int) -> list[str]:
    resolved_prefix = normalized_code(prefix)
    if not resolved_prefix.endswith("-"):
        resolved_prefix = f"{resolved_prefix}-"

    generated: list[str] = []
    seen: set[str] = set()
    while len(generated) < count:
        token = "".join(secrets.choice(ALPHABET) for _ in range(6))
        code = f"{resolved_prefix}{token}"
        if code in seen:
            continue
        seen.add(code)
        generated.append(code)
    return generated


def serialize_promo(promo: AdminPromoCode) -> dict[str, object]:
    return {
        "id": str(promo.id),
        "code": promo.code,
        "type": promo.promo_type,
        "value": float(promo.value),
        "product_id": promo.product_code,
        "max_uses": int(promo.max_uses),
        "uses_count": int(promo.uses_count),
        "valid_from": promo.valid_from.isoformat(),
        "valid_until": promo.valid_until.isoformat() if promo.valid_until else None,
        "channel_tag": promo.channel_tag,
        "status": promo.status,
        "created_at": promo.created_at.isoformat(),
    }


def to_decimal(value: float) -> Decimal:
    return Decimal(str(value))
