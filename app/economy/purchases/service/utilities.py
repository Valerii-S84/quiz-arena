from __future__ import annotations

from math import ceil
from uuid import uuid4

from app.economy.purchases.catalog import ProductSpec

from .constants import PREMIUM_PLAN_RANKS


def _build_invoice_payload() -> str:
    return f"inv_{uuid4().hex}"


def _premium_plan_rank(plan_code: str | None) -> int:
    return PREMIUM_PLAN_RANKS.get(plan_code or "", 0)


def _calculate_discount_amount(base_price: int, discount_percent: int) -> int:
    discounted = ceil(base_price * (100 - discount_percent) / 100)
    final_price = max(1, discounted)
    return max(0, base_price - final_price)


def _is_promo_scope_applicable(target_scope: str, *, product: ProductSpec) -> bool:
    if target_scope in {product.product_code, "ANY"}:
        return True
    if product.product_type == "MICRO" and target_scope == "MICRO_ANY":
        return True
    if product.product_type == "PREMIUM" and target_scope == "PREMIUM_ANY":
        return True
    return False
