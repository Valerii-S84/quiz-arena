from __future__ import annotations

from datetime import timezone
from uuid import uuid4

import pytest

from app.economy.purchases.errors import PurchaseNotFoundError, PurchasePrecheckoutValidationError
from app.economy.purchases.service import precheckout as purchase_precheckout
from tests.purchase_service_test_helpers import NOW, SessionStub, purchase_model


@pytest.mark.asyncio
async def test_mark_invoice_sent_rejects_missing_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_by_id_for_update(_session, _purchase_id):
        return None

    monkeypatch.setattr(
        purchase_precheckout.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )

    with pytest.raises(PurchaseNotFoundError):
        await purchase_precheckout.mark_invoice_sent(SessionStub(), purchase_id=uuid4())


@pytest.mark.asyncio
async def test_mark_invoice_sent_updates_created_purchase_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = purchase_model(status="CREATED")
    events: list[dict[str, object]] = []

    class _FixedDatetime:
        @staticmethod
        def now(tz):
            assert tz == timezone.utc
            return NOW

    async def _fake_get_by_id_for_update(_session, purchase_id):
        assert purchase_id == purchase.id
        return purchase

    async def _fake_emit_purchase_event(
        _session, *, event_type: str, purchase, happened_at, extra_payload=None
    ) -> None:
        assert extra_payload is None
        events.append(
            {"event_type": event_type, "purchase_id": purchase.id, "happened_at": happened_at}
        )

    monkeypatch.setattr(
        purchase_precheckout.PurchasesRepo, "get_by_id_for_update", _fake_get_by_id_for_update
    )
    monkeypatch.setattr(purchase_precheckout, "_emit_purchase_event", _fake_emit_purchase_event)
    monkeypatch.setattr(purchase_precheckout, "datetime", _FixedDatetime)

    await purchase_precheckout.mark_invoice_sent(SessionStub(), purchase_id=purchase.id)

    assert purchase.status == "INVOICE_SENT"
    assert events == [
        {"event_type": "purchase_invoice_sent", "purchase_id": purchase.id, "happened_at": NOW}
    ]


@pytest.mark.parametrize(
    ("purchase", "user_id", "total_amount"),
    [
        (None, 7, 5),
        (purchase_model(user_id=8), 7, 5),
        (purchase_model(stars_amount=6), 7, 5),
        (purchase_model(status="FAILED"), 7, 5),
    ],
)
@pytest.mark.asyncio
async def test_validate_precheckout_rejects_invalid_purchase_state(
    monkeypatch: pytest.MonkeyPatch,
    purchase,
    user_id: int,
    total_amount: int,
) -> None:
    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload: str):
        return purchase

    monkeypatch.setattr(
        purchase_precheckout.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_precheckout.validate_precheckout(
            SessionStub(),
            user_id=user_id,
            invoice_payload="inv-invalid",
            total_amount=total_amount,
            precheckout_query_id="pre-invalid",
            now_utc=NOW,
        )


@pytest.mark.asyncio
async def test_validate_precheckout_keeps_existing_ok_status_without_reemitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = purchase_model(
        status="PRECHECKOUT_OK",
        applied_promo_code_id=None,
        telegram_pre_checkout_query_id="pre-existing",
    )

    async def _fake_get_by_invoice_payload_for_update(_session, invoice_payload: str):
        assert invoice_payload == "inv-existing-ok"
        return purchase

    async def _fail_emit_purchase_event(*_args, **_kwargs) -> None:
        pytest.fail("precheckout ok purchase should not emit duplicate event")

    monkeypatch.setattr(
        purchase_precheckout.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )
    monkeypatch.setattr(purchase_precheckout, "_emit_purchase_event", _fail_emit_purchase_event)

    await purchase_precheckout.validate_precheckout(
        SessionStub(),
        user_id=purchase.user_id,
        invoice_payload="inv-existing-ok",
        total_amount=purchase.stars_amount,
        precheckout_query_id="pre-replayed",
        now_utc=NOW,
    )

    assert purchase.status == "PRECHECKOUT_OK"
    assert purchase.telegram_pre_checkout_query_id == "pre-existing"
