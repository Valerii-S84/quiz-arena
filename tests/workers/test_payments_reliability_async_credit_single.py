from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.economy.purchases.errors import ProductNotFoundError
from app.economy.purchases.recovery import MAX_CREDIT_RECOVERY_ATTEMPTS
from app.workers.tasks import payments_reliability_async
from tests.workers.payments_reliability_async_support import SessionLocalStub


@pytest.mark.asyncio
async def test_recover_single_purchase_returns_missing_when_purchase_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase_id = uuid4()
    now_utc = datetime.now(timezone.utc)
    session_local_stub = SessionLocalStub()

    async def _get_for_credit_lock(session: object, purchase_id: UUID) -> None:
        del session
        del purchase_id
        return None

    monkeypatch.setattr(
        payments_reliability_async,
        "SessionLocal",
        session_local_stub,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_for_credit_lock",
        _get_for_credit_lock,
    )

    result = await payments_reliability_async._recover_single_purchase(
        purchase_id,
        now_utc=now_utc,
    )

    assert result == "missing"


@pytest.mark.asyncio
async def test_recover_single_purchase_returns_skipped_when_status_is_not_paid_uncredited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase_id = uuid4()
    now_utc = datetime.now(timezone.utc)
    purchase = SimpleNamespace(
        status="CREATED",
        telegram_payment_charge_id="charge",
        raw_successful_payment={"foo": "bar"},
    )
    session_local_stub = SessionLocalStub()

    async def _get_for_credit_lock(session: object, purchase_id: UUID) -> SimpleNamespace:
        del session, purchase_id
        return purchase

    monkeypatch.setattr(
        payments_reliability_async,
        "SessionLocal",
        session_local_stub,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_for_credit_lock",
        _get_for_credit_lock,
    )

    result = await payments_reliability_async._recover_single_purchase(
        purchase_id,
        now_utc=now_utc,
    )

    assert result == "skipped"


@pytest.mark.asyncio
async def test_recover_single_purchase_marks_review_when_charge_id_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase_id = uuid4()
    purchase = SimpleNamespace(
        user_id=5,
        status="PAID_UNCREDITED",
        telegram_payment_charge_id=None,
        raw_successful_payment={"x": 1},
    )
    now_utc = datetime.now(timezone.utc)
    session_local_stub = SessionLocalStub()

    async def _get_for_credit_lock(session: object, purchase_id: UUID) -> SimpleNamespace:
        del session, purchase_id
        return purchase

    monkeypatch.setattr(
        payments_reliability_async,
        "SessionLocal",
        session_local_stub,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_for_credit_lock",
        _get_for_credit_lock,
    )

    result = await payments_reliability_async._recover_single_purchase(
        purchase_id,
        now_utc=now_utc,
    )

    assert result == "review"
    assert purchase.status == "FAILED_CREDIT_PENDING_REVIEW"


@pytest.mark.asyncio
async def test_recover_single_purchase_marks_review_when_raw_payment_not_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase_id = uuid4()
    purchase = SimpleNamespace(
        user_id=7,
        status="PAID_UNCREDITED",
        telegram_payment_charge_id="tg-charge",
        raw_successful_payment="not-a-dict",
    )
    now_utc = datetime.now(timezone.utc)
    session_local_stub = SessionLocalStub()

    async def _get_for_credit_lock(session: object, purchase_id: UUID) -> SimpleNamespace:
        del session, purchase_id
        return purchase

    monkeypatch.setattr(
        payments_reliability_async,
        "SessionLocal",
        session_local_stub,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_for_credit_lock",
        _get_for_credit_lock,
    )

    result = await payments_reliability_async._recover_single_purchase(
        purchase_id,
        now_utc=now_utc,
    )

    assert result == "review"
    assert purchase.status == "FAILED_CREDIT_PENDING_REVIEW"


@pytest.mark.asyncio
async def test_recover_single_purchase_credits_successful_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase_id = uuid4()
    purchase = SimpleNamespace(
        id=purchase_id,
        user_id=13,
        invoice_payload="invoice",
        telegram_payment_charge_id="tg-charge",
        raw_successful_payment={"x": 1},
        status="PAID_UNCREDITED",
    )
    now_utc = datetime.now(timezone.utc)
    session_local_stub = SessionLocalStub()
    called: list[dict[str, object]] = []

    async def _get_for_credit_lock(session: object, purchase_id: UUID) -> SimpleNamespace:
        del session, purchase_id
        return purchase

    async def _apply_successful_payment(
        session: object,
        *,
        user_id: int,
        invoice_payload: str,
        telegram_payment_charge_id: str,
        raw_successful_payment: dict[str, object],
        now_utc,
    ) -> None:
        del session
        called.append(
            {
                "user_id": user_id,
                "invoice_payload": invoice_payload,
                "telegram_payment_charge_id": telegram_payment_charge_id,
                "raw_successful_payment": raw_successful_payment,
                "now_utc": now_utc,
            }
        )

    monkeypatch.setattr(
        payments_reliability_async,
        "SessionLocal",
        session_local_stub,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_for_credit_lock",
        _get_for_credit_lock,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchaseService,
        "apply_successful_payment",
        _apply_successful_payment,
    )

    result = await payments_reliability_async._recover_single_purchase(
        purchase_id,
        now_utc=now_utc,
    )

    assert result == "credited"
    assert called == [
        {
            "user_id": purchase.user_id,
            "invoice_payload": purchase.invoice_payload,
            "telegram_payment_charge_id": "tg-charge",
            "raw_successful_payment": purchase.raw_successful_payment,
            "now_utc": now_utc,
        }
    ]


@pytest.mark.parametrize(
    "failures, expected",
    [
        (1, "retryable_failure"),
        (MAX_CREDIT_RECOVERY_ATTEMPTS, "review"),
    ],
)
@pytest.mark.asyncio
async def test_recover_single_purchase_marks_retryable_or_review_on_apply_error(
    monkeypatch: pytest.MonkeyPatch,
    failures: int,
    expected: str,
) -> None:
    purchase_id = uuid4()
    purchase = SimpleNamespace(
        user_id=19,
        status="PAID_UNCREDITED",
        telegram_payment_charge_id="tg-charge",
        invoice_payload="invoice",
        raw_successful_payment={"x": 1},
    )
    now_utc = datetime.now(timezone.utc)
    session_local_stub = SessionLocalStub()

    async def _get_for_credit_lock(session: object, purchase_id: UUID) -> SimpleNamespace:
        del session, purchase_id
        return purchase

    async def _apply_successful_payment(
        session: object,
        *,
        user_id: int,
        invoice_payload: str,
        telegram_payment_charge_id: str,
        raw_successful_payment: dict[str, object],
        now_utc,
    ) -> None:
        del session, user_id, invoice_payload, telegram_payment_charge_id, raw_successful_payment
        del now_utc
        raise ProductNotFoundError("recoverable")

    def _increment(
        raw_successful_payment: dict[str, object] | None
    ) -> tuple[dict[str, object], int]:
        del raw_successful_payment
        return {"_credit_recovery_failures": failures}, failures

    monkeypatch.setattr(
        payments_reliability_async,
        "SessionLocal",
        session_local_stub,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_for_credit_lock",
        _get_for_credit_lock,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchaseService,
        "apply_successful_payment",
        _apply_successful_payment,
    )
    monkeypatch.setattr(
        payments_reliability_async,
        "increment_recovery_failures",
        _increment,
    )

    result = await payments_reliability_async._recover_single_purchase(
        purchase_id,
        now_utc=now_utc,
    )

    assert result == expected
    if expected == "review":
        assert purchase.status == "FAILED_CREDIT_PENDING_REVIEW"
