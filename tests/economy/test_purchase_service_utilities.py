from __future__ import annotations

from types import SimpleNamespace

from app.economy.purchases.catalog import ProductSpec
from app.economy.purchases.service.utilities import (
    _calculate_discount_amount,
    _calculate_discount_amount_for_promo,
    _is_promo_scope_applicable,
    _premium_plan_rank,
)


def _promo_code(**overrides: object) -> SimpleNamespace:
    payload: dict[str, object] = {
        "promo_type": "PERCENT_DISCOUNT",
        "discount_type": None,
        "discount_value": None,
        "discount_percent": 50,
        "target_scope": "ANY",
        "applicable_products": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _product(*, product_code: str, product_type: str) -> ProductSpec:
    return ProductSpec(
        product_code=product_code,
        product_type=product_type,
        title=product_code,
        description=product_code,
        stars_amount=10,
        energy_credit=0,
    )


def test_calculate_discount_amount_handles_free_fixed_and_percent() -> None:
    assert _calculate_discount_amount(99, discount_type="FREE", discount_value=None) == 99
    assert _calculate_discount_amount(99, discount_type="FIXED", discount_value=150) == 99
    assert _calculate_discount_amount(99, discount_type="FIXED", discount_value=-5) == 0
    assert _calculate_discount_amount(5, discount_type="PERCENT", discount_value=50) == 2
    assert _calculate_discount_amount(5, discount_type="PERCENT", discount_value=110) == 5
    assert _calculate_discount_amount(5, discount_type="PERCENT", discount_value=-1) == 0


def test_calculate_discount_amount_for_promo_uses_runtime_discount_resolution() -> None:
    promo_code = _promo_code(discount_type="FIXED", discount_value=3, discount_percent=None)

    assert _calculate_discount_amount_for_promo(5, promo_code=promo_code) == 3


def test_is_promo_scope_applicable_honors_explicit_product_lists() -> None:
    promo_code = _promo_code(
        target_scope="MULTI", applicable_products=["ENERGY_10", "MEGA_PACK_15"]
    )

    assert _is_promo_scope_applicable(
        promo_code,
        product=_product(product_code="ENERGY_10", product_type="MICRO"),
    )
    assert not _is_promo_scope_applicable(
        promo_code,
        product=_product(product_code="PREMIUM_MONTH", product_type="PREMIUM"),
    )


def test_is_promo_scope_applicable_honors_any_and_type_scopes() -> None:
    assert _is_promo_scope_applicable(
        _promo_code(target_scope="ANY"),
        product=_product(product_code="ENERGY_10", product_type="MICRO"),
    )
    assert _is_promo_scope_applicable(
        _promo_code(target_scope="MICRO_ANY"),
        product=_product(product_code="ENERGY_10", product_type="MICRO"),
    )
    assert not _is_promo_scope_applicable(
        _promo_code(target_scope="MICRO_ANY"),
        product=_product(product_code="PREMIUM_MONTH", product_type="PREMIUM"),
    )
    assert _is_promo_scope_applicable(
        _promo_code(target_scope="PREMIUM_ANY"),
        product=_product(product_code="PREMIUM_MONTH", product_type="PREMIUM"),
    )


def test_premium_plan_rank_returns_zero_for_unknown_or_empty_plan() -> None:
    assert _premium_plan_rank(None) == 0
    assert _premium_plan_rank("UNKNOWN") == 0
    assert _premium_plan_rank("PREMIUM_YEAR") > _premium_plan_rank("PREMIUM_MONTH")
