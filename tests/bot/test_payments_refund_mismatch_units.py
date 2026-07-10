from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from aiogram.types import RefundedPayment

from app.bot.handlers import payments_runtime
from app.economy.purchases.errors import PurchaseRefundValidationError
from tests.bot.helpers import DummySessionLocal


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict[str, object]]] = []

    def warning(self, event: str, **payload: object) -> None:
        self.warnings.append((event, payload))


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
async def test_refund_payment_update_rejects_invoice_payload_amount_mismatch_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    refund = _refunded_payment(total_amount=30)
    purchase = SimpleNamespace(
        id=UUID("123e4567-e89b-12d3-a456-426614174005"),
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
        return None

    async def _fake_get_by_invoice_payload(_session, invoice_payload: str):
        assert invoice_payload == refund.invoice_payload
        return purchase

    async def _fake_refund_purchase(*_args, **_kwargs):
        raise AssertionError("invoice payload match alone must not reach refund_purchase")

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

    assert purchase.status == "PRECHECKOUT_OK"
    assert purchase.telegram_payment_charge_id is None
    assert purchase.paid_at is None


@pytest.mark.asyncio
async def test_refund_payment_update_logs_mismatch_rejection_without_raw_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    refund = _refunded_payment(currency="USD")
    purchase = SimpleNamespace(
        id=UUID("123e4567-e89b-12d3-a456-426614174006"),
        user_id=77,
        invoice_payload=refund.invoice_payload,
        telegram_payment_charge_id=None,
        status="PRECHECKOUT_OK",
        paid_at=None,
        currency="XTR",
        stars_amount=29,
    )
    logger = _Logger()

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=77)

    async def _fake_get_by_charge_id(_session, _telegram_payment_charge_id: str):
        return purchase

    async def _fake_refund_purchase(*_args, **_kwargs):
        raise AssertionError("mismatch must not reach refund_purchase")

    monkeypatch.setattr(payments_runtime, "logger", logger)
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

    assert logger.warnings[0][0] == "payment_refund_update_validation_rejected"
    payload = logger.warnings[0][1]
    assert payload["reason"] == "currency_mismatch"
    assert payload["expected_currency"] == "XTR"
    assert payload["refunded_currency"] == "USD"
    assert payload["expected_total_amount"] == 29
    assert payload["refunded_total_amount"] == 29
    assert payload["purchase_id_hash"] != str(purchase.id)
    assert payload["telegram_payment_charge_id_hash"] != refund.telegram_payment_charge_id
    assert "purchase_id" not in payload
    assert "telegram_payment_charge_id" not in payload
    assert str(purchase.id) not in str(logger.warnings)
    assert refund.telegram_payment_charge_id not in str(logger.warnings)
