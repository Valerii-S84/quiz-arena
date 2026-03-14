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
    premium_days: int = 0
    grants_streak_saver: bool = False
    friend_challenge_tickets: int = 0


PRODUCTS: dict[str, ProductSpec] = {
    "ENERGY_10": ProductSpec(
        product_code="ENERGY_10",
        product_type="MICRO",
        title="+10 Energie",
        description="Sofort weiterspielen mit +10 Energie.",
        stars_amount=5,
        energy_credit=10,
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
    "FRIEND_CHALLENGE_5": ProductSpec(
        product_code="FRIEND_CHALLENGE_5",
        product_type="MICRO",
        title="Duell Ticket",
        description="Ein zusaetzliches Freundes-Duell.",
        stars_amount=5,
        energy_credit=0,
        friend_challenge_tickets=1,
    ),
    "PREMIUM_STARTER": ProductSpec(
        product_code="PREMIUM_STARTER",
        product_type="PREMIUM",
        title="Premium Starter",
        description="7 Tage Premium ohne Limits.",
        stars_amount=29,
        energy_credit=0,
        premium_days=7,
    ),
    "PREMIUM_MONTH": ProductSpec(
        product_code="PREMIUM_MONTH",
        product_type="PREMIUM",
        title="Premium Month",
        description="30 Tage Premium ohne Limits.",
        stars_amount=99,
        energy_credit=0,
        premium_days=30,
    ),
    "PREMIUM_SEASON": ProductSpec(
        product_code="PREMIUM_SEASON",
        product_type="PREMIUM",
        title="Premium Season",
        description="90 Tage Premium ohne Limits.",
        stars_amount=249,
        energy_credit=0,
        premium_days=90,
    ),
    "PREMIUM_YEAR": ProductSpec(
        product_code="PREMIUM_YEAR",
        product_type="PREMIUM",
        title="Premium Year",
        description="365 Tage Premium ohne Limits.",
        stars_amount=499,
        energy_credit=0,
        premium_days=365,
    ),
}

SOFT_DISABLED_PRODUCT_CODES: frozenset[str] = frozenset(
    {
        "PREMIUM_SEASON",
        "PREMIUM_YEAR",
    }
)


def get_product(product_code: str) -> ProductSpec | None:
    return PRODUCTS.get(product_code)


def is_product_available_for_sale(product_code: str) -> bool:
    return product_code in PRODUCTS and product_code not in SOFT_DISABLED_PRODUCT_CODES
