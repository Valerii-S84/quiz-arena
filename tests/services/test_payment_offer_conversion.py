from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services import payment_offer_conversion


@pytest.mark.asyncio
async def test_mark_payment_offer_conversion_extracts_offer_key(monkeypatch) -> None:
    purchase_id = UUID("123e4567-e89b-12d3-a456-426614174099")
    calls: list[dict[str, object]] = []

    async def _fake_get_by_id(_session, _purchase_id):
        return SimpleNamespace(idempotency_key="buy:abcd1234:offer:91:deadbeef10")

    async def _fake_mark_converted_purchase(
        _session, *, user_id: int, impression_id: int, purchase_id: UUID
    ) -> bool:
        calls.append(
            {
                "user_id": user_id,
                "impression_id": impression_id,
                "purchase_id": purchase_id,
            }
        )
        return True

    monkeypatch.setattr(
        payment_offer_conversion.PurchaseService,
        "get_by_id",
        _fake_get_by_id,
    )
    monkeypatch.setattr(
        payment_offer_conversion.OfferService,
        "mark_offer_converted_purchase",
        _fake_mark_converted_purchase,
    )

    await payment_offer_conversion.mark_payment_offer_conversion(
        object(),
        user_id=77,
        purchase_id=purchase_id,
    )

    assert calls == [
        {
            "user_id": 77,
            "impression_id": 91,
            "purchase_id": purchase_id,
        }
    ]


@pytest.mark.asyncio
async def test_mark_payment_offer_conversion_skips_non_offer_key(monkeypatch) -> None:
    calls: list[object] = []

    async def _fake_get_by_id(_session, _purchase_id):
        return SimpleNamespace(idempotency_key="buy:abcd1234:deadbeef10")

    async def _fake_mark_converted_purchase(*_args, **_kwargs) -> bool:
        calls.append(object())
        return True

    monkeypatch.setattr(
        payment_offer_conversion.PurchaseService,
        "get_by_id",
        _fake_get_by_id,
    )
    monkeypatch.setattr(
        payment_offer_conversion.OfferService,
        "mark_offer_converted_purchase",
        _fake_mark_converted_purchase,
    )

    await payment_offer_conversion.mark_payment_offer_conversion(
        object(),
        user_id=77,
        purchase_id=UUID("123e4567-e89b-12d3-a456-426614174099"),
    )

    assert calls == []
