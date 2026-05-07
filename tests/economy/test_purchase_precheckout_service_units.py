from __future__ import annotations

import pytest

from app.economy.purchases.errors import PurchasePrecheckoutValidationError
from app.economy.purchases.service import precheckout as purchase_precheckout
from tests.purchase_service_test_helpers import NOW, SessionStub, purchase_model


@pytest.mark.asyncio
async def test_validate_precheckout_marks_purchase_without_promo_ok_and_emits_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = purchase_model(
        status="CREATED",
        applied_promo_code_id=None,
        invoice_payload="inv_no_promo",
    )
    events: list[dict[str, object]] = []

    async def _fake_get_by_invoice_payload_for_update(_session, invoice_payload: str):
        assert invoice_payload == purchase.invoice_payload
        return purchase

    async def _fail_validate_reserved_discount(*_args, **_kwargs) -> None:
        pytest.fail("promo validation should not run when purchase has no promo")

    async def _fake_emit_purchase_event(
        _session,
        *,
        event_type: str,
        purchase,
        happened_at,
        extra_payload=None,
    ) -> None:
        assert extra_payload is None
        events.append(
            {
                "event_type": event_type,
                "purchase_id": purchase.id,
                "happened_at": happened_at,
            }
        )

    monkeypatch.setattr(
        purchase_precheckout.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )
    monkeypatch.setattr(
        purchase_precheckout,
        "_validate_reserved_discount_for_purchase",
        _fail_validate_reserved_discount,
    )
    monkeypatch.setattr(
        purchase_precheckout,
        "_emit_purchase_event",
        _fake_emit_purchase_event,
    )

    await purchase_precheckout.validate_precheckout(
        SessionStub(),
        user_id=purchase.user_id,
        invoice_payload=purchase.invoice_payload,
        total_amount=purchase.stars_amount,
        precheckout_query_id="pre-1",
        now_utc=NOW,
    )

    assert purchase.status == "PRECHECKOUT_OK"
    assert purchase.telegram_pre_checkout_query_id == "pre-1"
    assert events == [
        {
            "event_type": "purchase_precheckout_ok",
            "purchase_id": purchase.id,
            "happened_at": NOW,
        }
    ]


@pytest.mark.asyncio
async def test_validate_precheckout_rejects_expired_reserved_promo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = purchase_model(
        status="INVOICE_SENT",
        applied_promo_code_id=21,
        invoice_payload="inv_expired_reserve",
    )

    async def _fake_get_by_invoice_payload_for_update(_session, invoice_payload: str):
        assert invoice_payload == purchase.invoice_payload
        return purchase

    async def _fake_validate_reserved_discount(*_args, **_kwargs):
        raise PurchasePrecheckoutValidationError

    async def _fail_emit_purchase_event(*_args, **_kwargs) -> None:
        pytest.fail("precheckout event must not be emitted for invalid promo reserve")

    monkeypatch.setattr(
        purchase_precheckout.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )
    monkeypatch.setattr(
        purchase_precheckout,
        "_validate_reserved_discount_for_purchase",
        _fake_validate_reserved_discount,
    )
    monkeypatch.setattr(
        purchase_precheckout,
        "_emit_purchase_event",
        _fail_emit_purchase_event,
    )

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_precheckout.validate_precheckout(
            SessionStub(),
            user_id=purchase.user_id,
            invoice_payload=purchase.invoice_payload,
            total_amount=purchase.stars_amount,
            precheckout_query_id="pre-expired",
            now_utc=NOW,
        )

    assert purchase.status == "INVOICE_SENT"
