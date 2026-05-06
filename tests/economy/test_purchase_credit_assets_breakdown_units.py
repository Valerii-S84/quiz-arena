from __future__ import annotations

from app.economy.purchases.catalog import ProductSpec
from app.economy.purchases.service.credit_assets import build_asset_breakdown


def test_build_asset_breakdown_collects_all_non_zero_assets() -> None:
    product = ProductSpec(
        product_code="COMBO",
        product_type="MICRO",
        title="Combo",
        description="Combo",
        stars_amount=25,
        energy_credit=10,
        premium_days=7,
        grants_streak_saver=True,
        friend_challenge_tickets=2,
    )

    assert build_asset_breakdown(product) == {
        "paid_energy": 10,
        "premium_days": 7,
        "streak_saver_tokens": 1,
        "friend_challenge_tickets": 2,
    }


def test_build_asset_breakdown_omits_zero_value_assets() -> None:
    product = ProductSpec(
        product_code="EMPTY",
        product_type="MICRO",
        title="Empty",
        description="Empty",
        stars_amount=0,
        energy_credit=0,
    )

    assert build_asset_breakdown(product) == {}
