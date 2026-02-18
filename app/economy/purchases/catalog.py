from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProductSpec:
    product_code: str
    product_type: str
    title: str
    description: str
    stars_amount: int
    energy_credit: int
    grants_streak_saver: bool = False
    grants_mega_mode_access: bool = False


MEGA_PACK_MODE_CODES = (
    "CASES_PRACTICE",
    "TRENNBARE_VERBEN",
    "WORD_ORDER",
)

PRODUCTS: dict[str, ProductSpec] = {
    "ENERGY_10": ProductSpec(
        product_code="ENERGY_10",
        product_type="MICRO",
        title="+10 Energie",
        description="Sofort weiterspielen mit +10 Energie.",
        stars_amount=10,
        energy_credit=10,
    ),
    "MEGA_PACK_15": ProductSpec(
        product_code="MEGA_PACK_15",
        product_type="MICRO",
        title="Mega Pack",
        description="+15 Energie und 3 Modi für 24 Stunden.",
        stars_amount=15,
        energy_credit=15,
        grants_mega_mode_access=True,
    ),
    "STREAK_SAVER_20": ProductSpec(
        product_code="STREAK_SAVER_20",
        product_type="MICRO",
        title="Streak Saver",
        description="Schützt deine Serie für einen Tag.",
        stars_amount=20,
        energy_credit=0,
        grants_streak_saver=True,
    ),
}


def get_product(product_code: str) -> ProductSpec | None:
    return PRODUCTS.get(product_code)
