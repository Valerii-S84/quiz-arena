from __future__ import annotations

from math import ceil
from uuid import uuid4

from app.db.models.promo_codes import PromoCode
from app.economy.promo.runtime import (
    resolve_applicable_products,
    resolve_discount_type,
    resolve_discount_value,
)
from app.economy.purchases.catalog import ProductSpec

from .constants import PREMIUM_PLAN_RANKS


def _build_invoice_payload() -> str:
    return f"inv_{uuid4().hex}"


def _premium_plan_rank(plan_code: str | None) -> int:
    return PREMIUM_PLAN_RANKS.get(plan_code or "", 0)


def _calculate_discount_amount(
    base_price: int, *, discount_type: str, discount_value: int | None
) -> int:
    if discount_type == "FREE":
        return base_price
    if discount_type == "FIXED":
        return min(base_price, max(0, discount_value or 0))
    percent_value = max(0, min(100, int(discount_value or 0)))
    discounted = ceil(base_price * (100 - percent_value) / 100)
    final_price = max(0, discounted)
    return max(0, base_price - final_price)


def _calculate_discount_amount_for_promo(base_price: int, *, promo_code: PromoCode) -> int:
    return _calculate_discount_amount(
        base_price,
        discount_type=resolve_discount_type(promo_code) or "PERCENT",
        discount_value=resolve_discount_value(promo_code),
    )


def _is_promo_scope_applicable(promo_code: PromoCode, *, product: ProductSpec) -> bool:
    applicable_products = resolve_applicable_products(promo_code)
    if applicable_products is not None:
        return product.product_code in applicable_products
    target_scope = promo_code.target_scope
    if target_scope in {product.product_code, "ANY"}:
        return True
    if product.product_type == "MICRO" and target_scope == "MICRO_ANY":
        return True
    if product.product_type == "PREMIUM" and target_scope == "PREMIUM_ANY":
        return True
    return False
