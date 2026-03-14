from __future__ import annotations

from app.economy.purchases.catalog import get_product

PROMO_PRODUCT_LABELS = {
    "ENERGY_10": "+10 Energie",
    "STREAK_SAVER_20": "Serien-Schutz",
    "FRIEND_CHALLENGE_5": "Duell-Ticket",
    "PREMIUM_STARTER": "Premium Start",
    "PREMIUM_MONTH": "Premium Monat",
    "PREMIUM_SEASON": "Premium Saison",
    "PREMIUM_YEAR": "Premium Jahr",
}


def get_promo_product_label(product_code: str) -> str | None:
    product = get_product(product_code)
    if product is None:
        return None
    return PROMO_PRODUCT_LABELS.get(product_code, product.title)
