from __future__ import annotations

import pytest

from app.bot.handlers.payments import (
    _build_purchase_idempotency_key,
    _extract_offer_impression_id_from_purchase_idempotency_key,
    _parse_buy_callback_data,
)


def test_parse_buy_callback_without_optional_payload() -> None:
    product_code, promo_redemption_id, offer_impression_id = _parse_buy_callback_data("buy:ENERGY_10")

    assert product_code == "ENERGY_10"
    assert promo_redemption_id is None
    assert offer_impression_id is None


def test_parse_buy_callback_with_promo_payload() -> None:
    product_code, promo_redemption_id, offer_impression_id = _parse_buy_callback_data(
        "buy:PREMIUM_MONTH:promo:123e4567-e89b-12d3-a456-426614174000"
    )

    assert product_code == "PREMIUM_MONTH"
    assert str(promo_redemption_id) == "123e4567-e89b-12d3-a456-426614174000"
    assert offer_impression_id is None


def test_parse_buy_callback_with_offer_payload() -> None:
    product_code, promo_redemption_id, offer_impression_id = _parse_buy_callback_data("buy:ENERGY_10:offer:987")

    assert product_code == "ENERGY_10"
    assert promo_redemption_id is None
    assert offer_impression_id == 987


def test_parse_buy_callback_raises_for_invalid_payload() -> None:
    with pytest.raises(ValueError):
        _parse_buy_callback_data("buy:ENERGY_10:offer:not-a-number")


def test_build_purchase_idempotency_key_embeds_offer_impression_id() -> None:
    key = _build_purchase_idempotency_key(
        product_code="ENERGY_10",
        callback_id="abc-callback-id",
        offer_impression_id=91,
    )

    assert key.startswith("buy:")
    assert ":offer:91:" in key
    assert len(key) <= 64


def test_extract_offer_impression_id_from_purchase_idempotency_key() -> None:
    key = "buy:abcd1234:offer:77:deadbeef10"
    assert _extract_offer_impression_id_from_purchase_idempotency_key(key) == 77


def test_extract_offer_impression_id_returns_none_for_non_offer_key() -> None:
    key = _build_purchase_idempotency_key(
        product_code="ENERGY_10",
        callback_id="abc-callback-id",
        offer_impression_id=None,
    )
    assert _extract_offer_impression_id_from_purchase_idempotency_key(key) is None
