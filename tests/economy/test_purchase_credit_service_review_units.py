from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.economy.purchases.service.credit as purchase_credit
import app.economy.purchases.service.credit_marked as credit_marked
import app.economy.purchases.service.payment_validation_review as payment_validation_review
from app.economy.purchases.errors import PurchasePrecheckoutValidationError
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc


class _Session(AsyncSessionStub):
    pass


def _purchase(
    *,
    status: str = "INVOICE_SENT",
    stars_amount: int = 5,
    invoice_payload: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=7,
        status=status,
        product_code="ENERGY_10",
        product_type="MICRO",
        stars_amount=stars_amount,
        discount_stars_amount=0,
        currency="XTR",
        invoice_payload=invoice_payload,
        paid_at=None,
        credited_at=None,
        telegram_payment_charge_id=None,
        raw_successful_payment=None,
    )


def _stub_validation_review(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_create_once(*_args, **_kwargs):
        return object(), True

    async def _fake_emit_purchase_event(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        payment_validation_review,
        "_emit_purchase_event",
        _fake_emit_purchase_event,
    )
    monkeypatch.setattr(
        payment_validation_review.PaymentReconciliationReviewsRepo,
        "create_once",
        _fake_create_once,
    )


@pytest.mark.asyncio
async def test_apply_successful_payment_rejects_non_xtr_currency_for_paid_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase(invoice_payload="inv-wrong-currency")
    _stub_validation_review(monkeypatch)

    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload):
        return purchase

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_credit.apply_successful_payment(
            _Session(),
            user_id=7,
            invoice_payload="inv-wrong-currency",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment={
                "invoice_payload": "inv-wrong-currency",
                "currency": "USD",
                "total_amount": 5,
            },
            now_utc=datetime.now(UTC),
        )

    assert purchase.status == "FAILED_CREDIT_PENDING_REVIEW"
    assert purchase.paid_at is not None
    assert purchase.raw_successful_payment["validation_error"] == "currency_mismatch"


@pytest.mark.asyncio
async def test_apply_successful_payment_rejects_mismatched_total_amount_for_paid_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase(invoice_payload="inv-wrong-total")
    _stub_validation_review(monkeypatch)

    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload):
        return purchase

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_credit.apply_successful_payment(
            _Session(),
            user_id=7,
            invoice_payload="inv-wrong-total",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment={
                "invoice_payload": "inv-wrong-total",
                "currency": "XTR",
                "total_amount": 6,
            },
            now_utc=datetime.now(UTC),
        )

    assert purchase.status == "FAILED_CREDIT_PENDING_REVIEW"
    assert purchase.paid_at is not None
    assert purchase.raw_successful_payment["validation_error"] == "total_amount_mismatch"


@pytest.mark.asyncio
async def test_apply_successful_payment_rejects_missing_payment_payload_for_paid_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase(invoice_payload="inv-missing-payment")
    _stub_validation_review(monkeypatch)

    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload):
        return purchase

    async def _fail_credit_purchase_assets(*_args, **_kwargs) -> None:
        pytest.fail("paid purchase without successful payment payload must not be credited")

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )
    monkeypatch.setattr(credit_marked, "credit_purchase_assets", _fail_credit_purchase_assets)

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_credit.apply_successful_payment(
            _Session(),
            user_id=7,
            invoice_payload="inv-missing-payment",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment={},
            now_utc=datetime.now(UTC),
        )

    assert purchase.status == "FAILED_CREDIT_PENDING_REVIEW"
    assert purchase.telegram_payment_charge_id == "charge-1"
    assert purchase.paid_at is not None
    assert purchase.raw_successful_payment["validation_error"] == "currency_mismatch"
