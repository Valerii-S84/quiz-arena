from __future__ import annotations

from app.economy.purchases.catalog import get_product

PROMO_PRODUCT_LABELS = {
    "ENERGY_10": "+10 Energie",
    "STREAK_SAVER_20": "Serien-Schutz",
    "FRIEND_CHALLENGE_5": "Duell-Ticket",
    "PREMIUM_WEEK": "Arena Pass 7 Tage",
    "PREMIUM_MONTH": "Arena Pass 30 Tage",
    "PREMIUM_SEASON": "Arena Pass Saison",
    "PREMIUM_YEAR": "Arena Pass Jahr",
}


def get_promo_product_label(product_code: str) -> str | None:
    product = get_product(product_code)
    if product is None:
        return None
    return PROMO_PRODUCT_LABELS.get(product_code, product.title)
