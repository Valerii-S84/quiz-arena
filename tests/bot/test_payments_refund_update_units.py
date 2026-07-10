from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from aiogram.types import RefundedPayment

from app.bot.handlers import payments_runtime
from app.economy.purchases.errors import PurchaseRefundValidationError
from tests.bot.helpers import DummySessionLocal


def _refunded_payment(
    *,
    invoice_payload: str = "inv-1",
    currency: str = "XTR",
    total_amount: int = 29,
) -> RefundedPayment:
    return RefundedPayment.model_construct(
        currency=currency,
        total_amount=total_amount,
        invoice_payload=invoice_payload,
        telegram_payment_charge_id="charge-1",
    )


@pytest.mark.asyncio
async def test_refund_payment_update_uses_charge_lookup_and_refund_service(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    purchase_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    refund = _refunded_payment()
    purchase = SimpleNamespace(
        id=purchase_id,
        user_id=77,
        invoice_payload=refund.invoice_payload,
        telegram_payment_charge_id=None,
        status="PAID_UNCREDITED",
        paid_at=now_utc,
        currency="XTR",
        stars_amount=29,
    )
    calls: list[dict[str, object]] = []

    async def _fake_home_snapshot(session, *, telegram_user):
        del session
        assert telegram_user.id == 270
        return SimpleNamespace(user_id=77)

    async def _fake_get_by_charge_id(_session, telegram_payment_charge_id: str):
        assert telegram_payment_charge_id == refund.telegram_payment_charge_id
        return purchase

    async def _fake_refund_purchase(
        _session,
        *,
        purchase_id: UUID,
        now_utc: datetime,
        provider_refund_confirmed: bool,
    ):
        calls.append(
            {
                "purchase_id": purchase_id,
                "now_utc": now_utc,
                "provider_refund_confirmed": provider_refund_confirmed,
            }
        )
        return SimpleNamespace(status="REFUNDED")

    monkeypatch.setattr(payments_runtime, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(
        payments_runtime.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_home_snapshot,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_telegram_payment_charge_id_for_update",
        _fake_get_by_charge_id,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    result = await payments_runtime.refund_payment_update(
        telegram_user=SimpleNamespace(id=270),  # type: ignore[arg-type]
        refunded_payment=refund,  # type: ignore[arg-type]
        now_utc=now_utc,
    )

    assert result.status == "REFUNDED"
    assert calls == [
        {
            "purchase_id": purchase_id,
            "now_utc": now_utc,
            "provider_refund_confirmed": True,
        }
    ]


@pytest.mark.asyncio
async def test_refund_payment_update_falls_back_to_invoice_payload_before_refund(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    purchase_id = UUID("123e4567-e89b-12d3-a456-426614174001")
    refund = _refunded_payment()
    purchase = SimpleNamespace(
        id=purchase_id,
        user_id=77,
        invoice_payload=refund.invoice_payload,
        telegram_payment_charge_id=None,
        status="PRECHECKOUT_OK",
        paid_at=None,
        currency="XTR",
        stars_amount=29,
    )
    calls: list[dict[str, object]] = []

    async def _fake_home_snapshot(session, *, telegram_user):
        del session
        assert telegram_user.id == 270
        return SimpleNamespace(user_id=77)

    async def _fake_get_by_charge_id(_session, telegram_payment_charge_id: str):
        assert telegram_payment_charge_id == refund.telegram_payment_charge_id
        return None

    async def _fake_get_by_invoice_payload(_session, invoice_payload: str):
        assert invoice_payload == refund.invoice_payload
        return purchase

    async def _fake_refund_purchase(
        _session,
        *,
        purchase_id: UUID,
        now_utc: datetime,
        provider_refund_confirmed: bool,
    ):
        assert purchase.status == "PAID_UNCREDITED"
        assert purchase.telegram_payment_charge_id == refund.telegram_payment_charge_id
        assert purchase.paid_at is None
        calls.append(
            {
                "purchase_id": purchase_id,
                "now_utc": now_utc,
                "provider_refund_confirmed": provider_refund_confirmed,
            }
        )
        return SimpleNamespace(status="REFUNDED")

    monkeypatch.setattr(payments_runtime, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(
        payments_runtime.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_home_snapshot,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_telegram_payment_charge_id_for_update",
        _fake_get_by_charge_id,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    result = await payments_runtime.refund_payment_update(
        telegram_user=SimpleNamespace(id=270),  # type: ignore[arg-type]
        refunded_payment=refund,  # type: ignore[arg-type]
        now_utc=now_utc,
    )

    assert result.status == "REFUNDED"
    assert calls == [
        {
            "purchase_id": purchase_id,
            "now_utc": now_utc,
            "provider_refund_confirmed": True,
        }
    ]


@pytest.mark.asyncio
async def test_refund_payment_update_rejects_invoice_fallback_charge_conflict(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    refund = _refunded_payment()
    purchase = SimpleNamespace(
        id=UUID("123e4567-e89b-12d3-a456-426614174002"),
        user_id=77,
        invoice_payload=refund.invoice_payload,
        telegram_payment_charge_id="other-charge",
        status="PAID_UNCREDITED",
        paid_at=now_utc,
        currency="XTR",
        stars_amount=29,
    )

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=77)

    async def _fake_get_by_charge_id(_session, _telegram_payment_charge_id: str):
        return None

    async def _fake_get_by_invoice_payload(_session, _invoice_payload: str):
        return purchase

    async def _fake_refund_purchase(*_args, **_kwargs):
        raise AssertionError("charge conflicts must not reach refund_purchase")

    monkeypatch.setattr(payments_runtime, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(
        payments_runtime.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_home_snapshot,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_telegram_payment_charge_id_for_update",
        _fake_get_by_charge_id,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    with pytest.raises(PurchaseRefundValidationError):
        await payments_runtime.refund_payment_update(
            telegram_user=SimpleNamespace(id=270),  # type: ignore[arg-type]
            refunded_payment=refund,  # type: ignore[arg-type]
            now_utc=now_utc,
        )


@pytest.mark.asyncio
async def test_refund_payment_update_rejects_currency_mismatch_without_mutation(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    refund = _refunded_payment(currency="USD")
    purchase = SimpleNamespace(
        id=UUID("123e4567-e89b-12d3-a456-426614174003"),
        user_id=77,
        invoice_payload=refund.invoice_payload,
        telegram_payment_charge_id=None,
        status="PRECHECKOUT_OK",
        paid_at=None,
        currency="XTR",
        stars_amount=29,
    )

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=77)

    async def _fake_get_by_charge_id(_session, _telegram_payment_charge_id: str):
        return purchase

    async def _fake_refund_purchase(*_args, **_kwargs):
        raise AssertionError("currency mismatch must not reach refund_purchase")

    monkeypatch.setattr(payments_runtime, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(
        payments_runtime.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_home_snapshot,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_telegram_payment_charge_id_for_update",
        _fake_get_by_charge_id,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    with pytest.raises(PurchaseRefundValidationError):
        await payments_runtime.refund_payment_update(
            telegram_user=SimpleNamespace(id=270),  # type: ignore[arg-type]
            refunded_payment=refund,  # type: ignore[arg-type]
            now_utc=now_utc,
        )

    assert purchase.status == "PRECHECKOUT_OK"
    assert purchase.telegram_payment_charge_id is None
    assert purchase.paid_at is None


@pytest.mark.asyncio
async def test_refund_payment_update_rejects_amount_mismatch_without_mutation(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    refund = _refunded_payment(total_amount=30)
    purchase = SimpleNamespace(
        id=UUID("123e4567-e89b-12d3-a456-426614174004"),
        user_id=77,
        invoice_payload=refund.invoice_payload,
        telegram_payment_charge_id=None,
        status="PRECHECKOUT_OK",
        paid_at=None,
        currency="XTR",
        stars_amount=29,
    )

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=77)

    async def _fake_get_by_charge_id(_session, _telegram_payment_charge_id: str):
        return purchase

    async def _fake_refund_purchase(*_args, **_kwargs):
        raise AssertionError("amount mismatch must not reach refund_purchase")

    monkeypatch.setattr(payments_runtime, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(
        payments_runtime.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_home_snapshot,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_telegram_payment_charge_id_for_update",
        _fake_get_by_charge_id,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    with pytest.raises(PurchaseRefundValidationError):
        await payments_runtime.refund_payment_update(
            telegram_user=SimpleNamespace(id=270),  # type: ignore[arg-type]
            refunded_payment=refund,  # type: ignore[arg-type]
            now_utc=now_utc,
        )

    assert purchase.status == "PRECHECKOUT_OK"
    assert purchase.telegram_payment_charge_id is None
    assert purchase.paid_at is None
