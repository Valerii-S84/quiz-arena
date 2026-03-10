from __future__ import annotations

from app.db.models.promo_codes import PromoCode


def resolve_discount_type(promo_code: PromoCode) -> str | None:
    if promo_code.promo_type == "PREMIUM_GRANT":
        return None
    return promo_code.discount_type or "PERCENT"


def resolve_discount_value(promo_code: PromoCode) -> int | None:
    if promo_code.promo_type == "PREMIUM_GRANT":
        return promo_code.grant_premium_days
    if promo_code.discount_value is not None:
        return promo_code.discount_value
    return promo_code.discount_percent


def resolve_applicable_products(promo_code: PromoCode) -> list[str] | None:
    if promo_code.applicable_products is not None:
        return [str(item) for item in promo_code.applicable_products]
    if promo_code.target_scope in {"ANY", "MULTI", "MICRO_ANY", "PREMIUM_ANY"}:
        return None
    return [promo_code.target_scope]
