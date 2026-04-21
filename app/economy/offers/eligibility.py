from __future__ import annotations

from app.economy.purchases.catalog import get_product, is_product_available_for_sale


def _premium_plan_rank(plan_code: str | None) -> int:
    product = get_product(plan_code or "")
    if product is None or product.product_type != "PREMIUM":
        return 0
    return product.premium_days


def is_offer_cta_eligible(
    product_code: str,
    *,
    active_premium_scope: str | None = None,
) -> bool:
    if not is_product_available_for_sale(product_code):
        return False

    if active_premium_scope is None:
        return True

    product = get_product(product_code)
    if product is None or product.product_type != "PREMIUM":
        return product is not None

    return _premium_plan_rank(product_code) > _premium_plan_rank(active_premium_scope)


def eligible_cta_product_codes(
    product_codes: tuple[str, ...],
    *,
    active_premium_scope: str | None = None,
) -> tuple[str, ...]:
    return tuple(
        code
        for code in product_codes
        if is_offer_cta_eligible(code, active_premium_scope=active_premium_scope)
    )
