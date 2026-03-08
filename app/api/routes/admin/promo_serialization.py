from __future__ import annotations

from datetime import datetime

from app.db.models.promo_codes import PromoCode


def masked_code(code_prefix: str) -> str:
    return f"{code_prefix}****"


def effective_discount_type(promo: PromoCode) -> str | None:
    if promo.promo_type == "PREMIUM_GRANT":
        return None
    return promo.discount_type or "PERCENT"


def effective_discount_value(promo: PromoCode) -> int | None:
    if promo.promo_type == "PREMIUM_GRANT":
        return promo.grant_premium_days
    if promo.discount_value is not None:
        return promo.discount_value
    return promo.discount_percent


def effective_applicable_products(promo: PromoCode) -> list[str] | None:
    if promo.applicable_products is not None:
        return [str(item) for item in promo.applicable_products]
    if promo.promo_type == "PERCENT_DISCOUNT" and promo.target_scope not in {"ANY", "MULTI"}:
        if promo.target_scope in {"MICRO_ANY", "PREMIUM_ANY"}:
            return None
        return [promo.target_scope]
    return None


def resolve_display_status(promo: PromoCode, *, now_utc: datetime) -> str:
    if promo.status == "PAUSED":
        return "inactive"
    if promo.status in {"EXPIRED", "DEPLETED"}:
        return "expired"
    if promo.valid_until <= now_utc:
        return "expired"
    if promo.max_total_uses is not None and promo.used_total >= promo.max_total_uses:
        return "expired"
    return "active"


def serialize_valid_until(*, promo: PromoCode, is_open_ended: bool) -> str | None:
    if is_open_ended:
        return None
    return promo.valid_until.isoformat()
