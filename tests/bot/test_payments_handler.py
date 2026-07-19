from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.bot.handlers import payments_duel_paywall
from app.bot.handlers.payments import (
    _build_purchase_idempotency_key,
    _duel_paywall_context_from_callback,
    _extract_offer_impression_id_from_purchase_idempotency_key,
    _is_duel_paywall_callback,
    _parse_buy_callback_data,
)
from app.game.arena_duels.analytics import ARENA_EVENT_PREMIUM_WEEK_CLICKED


def test_parse_buy_callback_without_optional_payload() -> None:
    product_code, promo_redemption_id, offer_impression_id = _parse_buy_callback_data(
        "buy:ENERGY_10"
    )

    assert product_code == "ENERGY_10"
    assert promo_redemption_id is None
    assert offer_impression_id is None


def test_parse_buy_callback_with_duel_context_payload() -> None:
    product_code, promo_redemption_id, offer_impression_id = _parse_buy_callback_data(
        "buy:PREMIUM_WEEK:duel:close_loss"
    )

    assert product_code == "PREMIUM_WEEK"
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
    product_code, promo_redemption_id, offer_impression_id = _parse_buy_callback_data(
        "buy:ENERGY_10:offer:987"
    )

    assert product_code == "ENERGY_10"
    assert promo_redemption_id is None
    assert offer_impression_id == 987


def test_parse_buy_callback_raises_for_invalid_payload() -> None:
    with pytest.raises(ValueError):
        _parse_buy_callback_data("buy:ENERGY_10:offer:not-a-number")


def test_duel_paywall_callback_context_is_explicit() -> None:
    assert _is_duel_paywall_callback(
        "buy:PREMIUM_WEEK:duel:close_loss",
        product_code="PREMIUM_WEEK",
    )
    assert _is_duel_paywall_callback("buy:PREMIUM_WEEK:duel", product_code="PREMIUM_WEEK")
    assert not _is_duel_paywall_callback("buy:PREMIUM_WEEK", product_code="PREMIUM_WEEK")
    assert not _is_duel_paywall_callback(
        "buy:PREMIUM_WEEK:offer:42",
        product_code="PREMIUM_WEEK",
    )
    assert not _is_duel_paywall_callback(
        "buy:PREMIUM_WEEK:duel:unknown_context",
        product_code="PREMIUM_WEEK",
    )
    assert not _is_duel_paywall_callback("buy:ENERGY_10:duel", product_code="ENERGY_10")


def test_duel_paywall_context_is_extracted_from_callback() -> None:
    assert (
        _duel_paywall_context_from_callback(
            "buy:PREMIUM_WEEK:duel:daily_cup_prep",
            product_code="PREMIUM_WEEK",
        )
        == "daily_cup_prep"
    )
    assert (
        _duel_paywall_context_from_callback(
            "buy:PREMIUM_WEEK:duel",
            product_code="PREMIUM_WEEK",
        )
        is None
    )


@pytest.mark.asyncio
async def test_emit_duel_paywall_click_payload_includes_context(monkeypatch) -> None:
    emitted: list[dict[str, object]] = []

    async def _fake_emit(_session, **kwargs):
        emitted.append(kwargs)

    monkeypatch.setattr(payments_duel_paywall, "emit_arena_analytics_event", _fake_emit)

    await payments_duel_paywall._emit_duel_paywall_click(
        object(),
        user_id=5,
        product_code="PREMIUM_WEEK",
        happened_at=datetime(2026, 7, 6, 12, 0, tzinfo=UTC),
        paywall_context="beaten_result",
    )

    payload = emitted[0]["payload"]
    assert emitted[0]["event_type"] == ARENA_EVENT_PREMIUM_WEEK_CLICKED
    assert payload == {
        "user_id": 5,
        "action": "buy",
        "access_type": "PREMIUM_WEEK",
        "paywall_context": "beaten_result",
    }


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
