from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.economy.offers.types import OfferSelection
from app.economy.purchases.catalog import get_product


def build_offer_keyboard(selection: OfferSelection) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for product_code in selection.cta_product_codes:
        product = get_product(product_code)
        if product is None:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{product.title} ({product.stars_amount}⭐)",
                    callback_data=f"buy:{product_code}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
