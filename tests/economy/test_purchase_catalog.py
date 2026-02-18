from __future__ import annotations

from app.economy.purchases.catalog import PRODUCTS, get_product


def test_purchase_catalog_contains_core_micro_products() -> None:
    assert {"ENERGY_10", "MEGA_PACK_15", "STREAK_SAVER_20"}.issubset(PRODUCTS)


def test_purchase_catalog_contains_core_premium_products() -> None:
    assert {"PREMIUM_STARTER", "PREMIUM_MONTH", "PREMIUM_SEASON", "PREMIUM_YEAR"}.issubset(PRODUCTS)


def test_get_product_returns_none_for_unknown_code() -> None:
    assert get_product("UNKNOWN") is None
