from __future__ import annotations

from math import ceil
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.promo_labels import get_promo_product_label
from app.economy.purchases.catalog import PRODUCTS, get_product, is_product_available_for_sale


def _resolve_target_product_codes(
    target_scope: str | None,
    *,
    applicable_products: list[str] | None,
) -> list[str]:
    if applicable_products is not None:
        return [product_code for product_code in applicable_products if product_code in PRODUCTS]
    if target_scope is None:
        return []
    if target_scope == "ANY":
        return list(PRODUCTS.keys())
    if target_scope == "MICRO_ANY":
        return [
            product_code for product_code, spec in PRODUCTS.items() if spec.product_type == "MICRO"
        ]
    if target_scope == "PREMIUM_ANY":
        return [
            product_code
            for product_code, spec in PRODUCTS.items()
            if spec.product_type == "PREMIUM"
        ]
    if target_scope in PRODUCTS:
        return [target_scope]
    return []


def _discounted_stars_amount(
    *,
    base_stars_amount: int,
    discount_type: str | None,
    discount_value: int | None,
) -> int:
    if discount_type == "FREE":
        return 0
    if discount_type == "FIXED":
        return max(0, base_stars_amount - max(0, discount_value or 0))
    discounted = ceil(base_stars_amount * (100 - max(0, min(100, discount_value or 0))) / 100)
    return max(0, discounted)


def build_promo_discount_keyboard(
    *,
    redemption_id: UUID,
    target_scope: str | None,
    discount_type: str | None = None,
    discount_value: int | None = None,
    applicable_products: list[str] | None = None,
    discount_percent: int | None = None,
) -> InlineKeyboardMarkup | None:
    if discount_type is None and discount_percent is not None:
        discount_type = "PERCENT"
        discount_value = discount_percent
    target_product_codes = _resolve_target_product_codes(
        target_scope,
        applicable_products=applicable_products,
    )
    if not target_product_codes:
        return None

    rows: list[list[InlineKeyboardButton]] = []
    redemption_token = redemption_id.hex
    for product_code in target_product_codes:
        if not is_product_available_for_sale(product_code):
            continue

        product = get_product(product_code)
        if product is None:
            continue

        product_label = get_promo_product_label(product_code)
        if product_label is None:
            continue

        stars_amount = product.stars_amount
        if discount_type is not None:
            stars_amount = _discounted_stars_amount(
                base_stars_amount=product.stars_amount,
                discount_type=discount_type,
                discount_value=discount_value,
            )

        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{product_label} ({stars_amount}⭐)",
                    callback_data=f"buy:{product_code}:promo:{redemption_token}",
                )
            ]
        )

    if not rows:
        return None
    rows.append([InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
