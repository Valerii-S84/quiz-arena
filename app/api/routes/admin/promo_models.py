from __future__ import annotations

import secrets
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.db.models.promo_codes import PromoCode
from app.economy.promo.batch import generate_raw_codes
from app.services.promo_codes import normalize_promo_code

from .promo_serialization import (
    effective_applicable_products,
    effective_discount_type,
    effective_discount_value,
    masked_code,
    resolve_display_status,
    serialize_valid_until,
)

OPEN_ENDED_VALID_UNTIL = datetime(9999, 12, 31, tzinfo=timezone.utc)
LEGACY_PERCENT_TYPES = {"discount_percent", "percent_discount", "PERCENT_DISCOUNT"}
LEGACY_GRANT_TYPES = {"bonus_subscription_days", "PREMIUM_GRANT", "premium_grant"}
PROMO_STATUS_VALUES = {"active", "inactive", "expired"}


class PromoCreateRequest(BaseModel):
    code: str = Field(min_length=4, max_length=64)
    campaign_name: str | None = Field(default=None, max_length=128)
    discount_type: str | None = Field(default=None, pattern="^(PERCENT|FIXED|FREE)$")
    discount_value: float | None = Field(default=None, gt=0)
    applicable_products: list[str] | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_total_uses: int = Field(default=0, ge=0)
    max_per_user: int = Field(default=1, ge=1)
    type: str | None = None
    value: float | None = Field(default=None, gt=0)
    product_id: str | None = None
    max_uses: int | None = Field(default=None, ge=0)
    channel_tag: str | None = Field(default=None, max_length=50)


class PromoBulkCreateRequest(BaseModel):
    count: int = Field(ge=1, le=1000)
    prefix: str | None = Field(default=None, max_length=6)
    campaign_name: str | None = Field(default=None, max_length=128)
    discount_type: str | None = Field(default=None, pattern="^(PERCENT|FIXED|FREE)$")
    discount_value: float | None = Field(default=None, gt=0)
    applicable_products: list[str] | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_total_uses: int = Field(default=0, ge=0)
    max_per_user: int = Field(default=1, ge=1)
    type: str | None = None
    value: float | None = Field(default=None, gt=0)
    product_id: str | None = None
    max_uses: int | None = Field(default=None, ge=0)
    channel_tag: str | None = Field(default=None, max_length=50)


class PromoPatchRequest(BaseModel):
    campaign_name: str | None = Field(default=None, max_length=128)
    discount_type: str | None = Field(default=None, pattern="^(PERCENT|FIXED|FREE)$")
    discount_value: float | None = Field(default=None, gt=0)
    applicable_products: list[str] | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_total_uses: int | None = Field(default=None, ge=0)
    max_per_user: int | None = Field(default=None, ge=1)
    type: str | None = None
    value: float | None = Field(default=None, gt=0)
    product_id: str | None = None
    max_uses: int | None = Field(default=None, ge=0)


class PromoRevokeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=256)


def build_promo_id() -> int:
    return secrets.randbelow(2**63 - 1) + 1


def normalized_code(raw: str) -> str:
    return normalize_promo_code(raw)


def raw_code_value(raw: str) -> str:
    return raw.strip().upper()


def build_generated_codes(*, prefix: str | None, count: int) -> list[str]:
    return generate_raw_codes(
        count=count,
        token_length=8,
        prefix=normalized_prefix(prefix),
    )


def normalized_prefix(prefix: str | None) -> str:
    return normalized_code(prefix or "")[:6]


def resolve_promo_type(raw_type: str | None) -> str:
    if raw_type in LEGACY_GRANT_TYPES:
        return "PREMIUM_GRANT"
    return "PERCENT_DISCOUNT"


def resolve_discount_type(
    payload: PromoCreateRequest | PromoBulkCreateRequest | PromoPatchRequest,
) -> str | None:
    if payload.discount_type is not None:
        return payload.discount_type
    if payload.type in LEGACY_PERCENT_TYPES:
        return "PERCENT"
    return None


def resolve_discount_value(
    payload: PromoCreateRequest | PromoBulkCreateRequest | PromoPatchRequest,
) -> int | None:
    raw_value = payload.discount_value if payload.discount_value is not None else payload.value
    if raw_value is None:
        return None
    integer_value = int(raw_value)
    if float(integer_value) != float(raw_value):
        raise ValueError("Discount value must be an integer")
    return integer_value


def resolve_max_total_uses(
    payload: PromoCreateRequest | PromoBulkCreateRequest | PromoPatchRequest,
) -> int | None:
    raw_value = payload.max_total_uses if payload.max_total_uses is not None else payload.max_uses
    if raw_value is None:
        return None
    return None if raw_value == 0 else raw_value


def resolve_applicable_products(
    payload: PromoCreateRequest | PromoBulkCreateRequest | PromoPatchRequest,
) -> list[str] | None:
    if payload.applicable_products is not None:
        cleaned = [item.strip().upper() for item in payload.applicable_products if item.strip()]
    elif payload.product_id:
        cleaned = [payload.product_id.strip().upper()]
    else:
        cleaned = []
    if not cleaned:
        return None
    return list(dict.fromkeys(cleaned))


def resolve_target_scope(*, promo_type: str, applicable_products: list[str] | None) -> str:
    if promo_type == "PREMIUM_GRANT":
        return "PREMIUM_ANY"
    if applicable_products is None:
        return "ANY"
    if len(applicable_products) == 1:
        return applicable_products[0]
    return "MULTI"


def serialize_promo(
    promo: PromoCode,
    *,
    raw_code: str | None = None,
    can_reveal_code: bool = False,
    now_utc: datetime | None = None,
) -> dict[str, object]:
    current_time = now_utc or datetime.now(timezone.utc)
    discount_type = effective_discount_type(promo)
    applicable_products = effective_applicable_products(promo)
    is_open_ended = promo.valid_until >= OPEN_ENDED_VALID_UNTIL
    legacy_type = (
        "bonus_subscription_days" if promo.promo_type == "PREMIUM_GRANT" else "discount_percent"
    )
    legacy_product_id = (
        None
        if applicable_products is None or len(applicable_products) != 1
        else applicable_products[0]
    )
    return {
        "id": promo.id,
        "code": masked_code(promo.code_prefix),
        "code_prefix": promo.code_prefix,
        "raw_code": raw_code,
        "can_reveal_code": can_reveal_code and promo.code_encrypted is not None,
        "campaign_name": promo.campaign_name,
        "discount_type": discount_type,
        "discount_value": effective_discount_value(promo),
        "applicable_products": applicable_products,
        "valid_from": promo.valid_from.isoformat(),
        "valid_until": serialize_valid_until(promo=promo, is_open_ended=is_open_ended),
        "max_total_uses": promo.max_total_uses or 0,
        "max_per_user": promo.max_uses_per_user,
        "used_total": promo.used_total,
        "status": resolve_display_status(promo, now_utc=current_time),
        "created_at": promo.created_at.isoformat(),
        "updated_at": promo.updated_at.isoformat(),
        "type": legacy_type,
        "value": effective_discount_value(promo),
        "product_id": legacy_product_id,
        "target_scope": promo.target_scope,
        "max_uses": promo.max_total_uses or 0,
        "uses_count": promo.used_total,
        "channel_tag": None,
    }
