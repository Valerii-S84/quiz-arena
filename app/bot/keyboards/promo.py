from __future__ import annotations

from math import ceil
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.economy.purchases.catalog import PRODUCTS, get_product


def _resolve_target_product_codes(target_scope: str | None) -> list[str]:
    if target_scope is None:
        return []
    if target_scope == "ANY":
        return list(PRODUCTS.keys())
    if target_scope == "MICRO_ANY":
        return [product_code for product_code, spec in PRODUCTS.items() if spec.product_type == "MICRO"]
    if target_scope == "PREMIUM_ANY":
        return [product_code for product_code, spec in PRODUCTS.items() if spec.product_type == "PREMIUM"]
    if target_scope in PRODUCTS:
        return [target_scope]
    return []


def _discounted_stars_amount(*, base_stars_amount: int, discount_percent: int) -> int:
    discounted = ceil(base_stars_amount * (100 - discount_percent) / 100)
    return max(1, discounted)


def build_promo_discount_keyboard(
    *,
    redemption_id: UUID,
    target_scope: str | None,
    discount_percent: int | None,
) -> InlineKeyboardMarkup | None:
    target_product_codes = _resolve_target_product_codes(target_scope)
    if not target_product_codes:
        return None

    rows: list[list[InlineKeyboardButton]] = []
    for product_code in target_product_codes:
        product = get_product(product_code)
        if product is None:
            continue

        stars_amount = product.stars_amount
        if discount_percent is not None:
            stars_amount = _discounted_stars_amount(
                base_stars_amount=product.stars_amount,
                discount_percent=discount_percent,
            )

        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{product.title} ({stars_amount}⭐)",
                    callback_data=f"buy:{product_code}:promo:{redemption_id}",
                )
            ]
        )

    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)
