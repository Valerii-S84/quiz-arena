from __future__ import annotations

from app.economy.purchases.catalog import (
    LEGACY_PRODUCT_CODE_PREMIUM_STARTER,
    PRODUCTS,
    canonical_product_code,
    get_product,
    is_product_available_for_sale,
)


def test_purchase_catalog_contains_core_micro_products() -> None:
    assert {
        "ENERGY_10",
        "STREAK_SAVER_20",
        "FRIEND_CHALLENGE_5",
    }.issubset(PRODUCTS)
    assert PRODUCTS["FRIEND_CHALLENGE_5"].title == "Duell-Ticket"
    assert PRODUCTS["FRIEND_CHALLENGE_5"].description == "Ein zusätzliches Duell."


def test_purchase_catalog_contains_core_premium_products() -> None:
    assert {
        "PREMIUM_3_DAYS",
        "PREMIUM_WEEK",
        "PREMIUM_MONTH",
        "PREMIUM_SEASON",
        "PREMIUM_YEAR",
    }.issubset(PRODUCTS)
    assert PRODUCTS["PREMIUM_3_DAYS"].title == "Arena Pass 3 Tage"
    assert PRODUCTS["PREMIUM_WEEK"].title == "Arena Pass 7 Tage"
    assert PRODUCTS["PREMIUM_MONTH"].title == "Arena Pass 30 Tage"
    assert PRODUCTS["PREMIUM_SEASON"].title == "Arena Pass Saison"
    assert PRODUCTS["PREMIUM_YEAR"].title == "Arena Pass Jahr"
    assert PRODUCTS["PREMIUM_WEEK"].description == (
        "7 Tage ohne Duell-Limit. Mehr Revanchen. Mehr Arena-Chancen."
    )


def test_get_product_returns_none_for_unknown_code() -> None:
    assert get_product("UNKNOWN") is None


def test_legacy_premium_starter_alias_resolves_to_premium_week() -> None:
    product = get_product(LEGACY_PRODUCT_CODE_PREMIUM_STARTER)

    assert product is not None
    assert product.product_code == "PREMIUM_WEEK"
    assert canonical_product_code(LEGACY_PRODUCT_CODE_PREMIUM_STARTER) == "PREMIUM_WEEK"
    assert is_product_available_for_sale(LEGACY_PRODUCT_CODE_PREMIUM_STARTER) is False


def test_all_catalog_products_are_available_for_sale() -> None:
    assert is_product_available_for_sale("ENERGY_10") is True
    assert is_product_available_for_sale("PREMIUM_3_DAYS") is False
    assert is_product_available_for_sale("PREMIUM_WEEK") is True
    assert is_product_available_for_sale("PREMIUM_MONTH") is True
    assert is_product_available_for_sale("PREMIUM_SEASON") is True
    assert is_product_available_for_sale("PREMIUM_YEAR") is True


def test_premium_catalog_descriptions_explain_clear_benefits() -> None:
    assert PRODUCTS["PREMIUM_3_DAYS"].stars_amount == 0
    assert "Streak Freeze" in PRODUCTS["PREMIUM_3_DAYS"].description
    assert "Duell-Limit" in PRODUCTS["PREMIUM_WEEK"].description
    assert "ohne Pausen" in PRODUCTS["PREMIUM_MONTH"].description
    assert "spare Sterne" in PRODUCTS["PREMIUM_SEASON"].description
    assert "besten Sterne-Preis" in PRODUCTS["PREMIUM_YEAR"].description
