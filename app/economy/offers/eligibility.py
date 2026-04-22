from __future__ import annotations

from app.economy.purchases.catalog import ProductSpec, get_product, is_product_available_for_sale


def _get_premium_product(product_code: str | None) -> ProductSpec | None:
    product = get_product(product_code or "")
    if product is None or product.product_type != "PREMIUM":
        return None
    return product


def is_offer_cta_eligible(
    product_code: str,
    *,
    active_premium_scope: str | None = None,
) -> bool:
    if not is_product_available_for_sale(product_code):
        return False

    product = get_product(product_code)
    if product is None:
        return False

    if product.product_type != "PREMIUM":
        return True

    if active_premium_scope is None:
        return True

    active_premium_product = _get_premium_product(active_premium_scope)
    if active_premium_product is None:
        return False

    return product.premium_days > active_premium_product.premium_days


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
