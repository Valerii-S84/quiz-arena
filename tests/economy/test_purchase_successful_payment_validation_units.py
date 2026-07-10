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


def _purchase() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=7,
        status="INVOICE_SENT",
        product_code="ENERGY_10",
        stars_amount=5,
        currency="XTR",
        invoice_payload="inv-1",
        paid_at=None,
        credited_at=None,
        telegram_payment_charge_id=None,
        raw_successful_payment=None,
    )


def _successful_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "invoice_payload": "inv-1",
        "currency": "XTR",
        "total_amount": 5,
        "telegram_payment_charge_id": "raw-charge-in-payload",
        "order_info": {"email": "buyer@example.com", "phone_number": "+49123456789"},
    }
    payload.update(overrides)
    return payload


def _wire_purchase(monkeypatch: pytest.MonkeyPatch, purchase: SimpleNamespace) -> list[dict]:
    reviews: list[dict] = []

    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload):
        return purchase

    async def _fake_emit_purchase_event(*_args, **_kwargs) -> None:
        return None

    async def _fake_review_create_once(_session, **kwargs):
        reviews.append(kwargs)
        return object(), True

    async def _fail_credit_assets(*_args, **_kwargs) -> None:
        raise AssertionError("invalid payment evidence must not credit assets")

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )
    monkeypatch.setattr(
        payment_validation_review,
        "_emit_purchase_event",
        _fake_emit_purchase_event,
    )
    monkeypatch.setattr(credit_marked, "credit_purchase_assets", _fail_credit_assets)
    monkeypatch.setattr(
        payment_validation_review.PaymentReconciliationReviewsRepo,
        "create_once",
        _fake_review_create_once,
    )
    return reviews


@pytest.mark.asyncio
async def test_missing_total_amount_marks_review_without_crediting(monkeypatch) -> None:
    purchase = _purchase()
    reviews = _wire_purchase(monkeypatch, purchase)
    raw_payload = _successful_payload()
    raw_payload.pop("total_amount")

    result = await purchase_credit.mark_successful_payment_paid_uncredited(
        _Session(),
        user_id=7,
        invoice_payload="inv-1",
        telegram_payment_charge_id="charge-1",
        raw_successful_payment=raw_payload,
        now_utc=datetime.now(UTC),
    )

    assert result.status == "FAILED_CREDIT_PENDING_REVIEW"
    assert purchase.status == "FAILED_CREDIT_PENDING_REVIEW"
    assert purchase.credited_at is None
    assert purchase.paid_at is not None
    assert purchase.raw_successful_payment["validation_error"] == "missing_total_amount"
    assert purchase.raw_successful_payment["raw_payload_stored"] is False
    assert "invoice_payload" not in purchase.raw_successful_payment
    assert "telegram_payment_charge_id" not in purchase.raw_successful_payment
    assert "order_info" not in purchase.raw_successful_payment
    assert "buyer@example.com" not in repr(purchase.raw_successful_payment)
    assert reviews[0]["reason"] == "missing_total_amount"
    assert reviews[0]["transaction_id_hash"] != "charge-1"
    assert reviews[0]["safe_payload"]["invoice_payload_hash"] != "inv-1"
    assert "invoice_payload" not in reviews[0]["safe_payload"]
    assert "inv-1" not in repr(reviews)
    assert "charge-1" not in repr(reviews)
    assert "buyer@example.com" not in repr(reviews)


@pytest.mark.parametrize(
    ("payload_override", "expected_reason"),
    [
        ({"total_amount": 6}, "total_amount_mismatch"),
        ({"currency": "USD"}, "currency_mismatch"),
    ],
)
@pytest.mark.asyncio
async def test_wrong_amount_or_currency_raises_without_crediting(
    monkeypatch: pytest.MonkeyPatch,
    payload_override: dict[str, object],
    expected_reason: str,
) -> None:
    purchase = _purchase()
    _wire_purchase(monkeypatch, purchase)

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_credit.apply_successful_payment(
            _Session(),
            user_id=7,
            invoice_payload="inv-1",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment=_successful_payload(**payload_override),
            now_utc=datetime.now(UTC),
        )

    assert purchase.status == "FAILED_CREDIT_PENDING_REVIEW"
    assert purchase.credited_at is None
    assert purchase.raw_successful_payment["validation_error"] == expected_reason
