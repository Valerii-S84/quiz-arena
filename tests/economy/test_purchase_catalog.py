from __future__ import annotations

from app.economy.purchases.catalog import PRODUCTS, get_product, is_product_available_for_sale


def test_purchase_catalog_contains_core_micro_products() -> None:
    assert {
        "ENERGY_10",
        "STREAK_SAVER_20",
        "FRIEND_CHALLENGE_5",
    }.issubset(PRODUCTS)


def test_purchase_catalog_contains_core_premium_products() -> None:
    assert {
        "PREMIUM_STARTER",
        "PREMIUM_MONTH",
        "PREMIUM_SEASON",
        "PREMIUM_YEAR",
    }.issubset(PRODUCTS)


def test_get_product_returns_none_for_unknown_code() -> None:
    assert get_product("UNKNOWN") is None


def test_soft_disabled_products_are_not_available_for_sale() -> None:
    assert is_product_available_for_sale("ENERGY_10") is True
    assert is_product_available_for_sale("PREMIUM_MONTH") is True
    assert is_product_available_for_sale("PREMIUM_SEASON") is False
    assert is_product_available_for_sale("PREMIUM_YEAR") is False
