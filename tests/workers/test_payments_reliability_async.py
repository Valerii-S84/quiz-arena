from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from uuid import UUID

import pytest

from app.economy.purchases.errors import (
    ProductNotFoundError,
)
from app.economy.purchases.recovery import MAX_CREDIT_RECOVERY_ATTEMPTS
from app.workers.tasks import payments_reliability_async


class _SessionContextStub:
    def __init__(self, session: object, *, fail_on_commit: bool = False) -> None:
        self._session = session
        self._fail_on_commit = fail_on_commit

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None and self._fail_on_commit:
            raise RuntimeError("commit failed")
        return False


class _SessionLocalStub:
    def __init__(self, *, fail_on_commit_calls: tuple[int, ...] = ()) -> None:
        self._call_count = 0
        self._fail_on_commit_calls = set(fail_on_commit_calls)

    def begin(self) -> _SessionContextStub:
        self._call_count += 1
        return _SessionContextStub(
            object(),
            fail_on_commit=self._call_count in self._fail_on_commit_calls,
        )


@pytest.mark.asyncio
async def test_expire_stale_unpaid_invoices_async_counts_expired_invoices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_local_stub = _SessionLocalStub()
    logged: list[dict[str, object]] = []

    async def _expired(session: object, *, older_than_utc) -> int:
        del session, older_than_utc
        return 4

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", session_local_stub)
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "expire_stale_unpaid_invoices",
        _expired,
    )
    monkeypatch.setattr(
        payments_reliability_async.logger,
        "info",
        lambda event, **kwargs: logged.append({"event": event, **kwargs}),
    )

    result = await payments_reliability_async.expire_stale_unpaid_invoices_async(stale_minutes=30)

    assert result == {"expired_invoices": 4}
    assert logged == [{"event": "stale_unpaid_invoices_expiry_finished", "expired_invoices": 4}]


@pytest.mark.asyncio
async def test_run_refund_promo_rollback_async_counts_each_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = uuid4()
    skipped_by_status = uuid4()
    skipped_by_promo = uuid4()
    rolled_back = uuid4()
    not_rolled_back = uuid4()
    session_local_stub = _SessionLocalStub()

    async def _get_purchase_ids(session: object, *, limit: int) -> list[UUID]:
        del session, limit
        return [missing, skipped_by_status, skipped_by_promo, rolled_back, not_rolled_back]

    async def _get_purchase(session: object, purchase_id: UUID) -> SimpleNamespace | None:
        del session
        if purchase_id == missing:
            return None
        if purchase_id == skipped_by_status:
            return SimpleNamespace(
                id=skipped_by_status,
                status="CREATED",
                applied_promo_code_id=99,
            )
        if purchase_id == skipped_by_promo:
            return SimpleNamespace(
                id=skipped_by_promo,
                status="REFUNDED",
                applied_promo_code_id=None,
            )
        if purchase_id == not_rolled_back:
            return SimpleNamespace(
                id=not_rolled_back,
                status="REFUNDED",
                applied_promo_code_id=222,
            )
        return SimpleNamespace(
            id=rolled_back,
            status="REFUNDED",
            applied_promo_code_id=111,
        )

    async def _revoke_redemption(
        session: object,
        *,
        purchase_id: UUID,
        promo_code_id: int,
        now_utc,
    ) -> tuple[None, None, bool]:
        del session, now_utc
        assert promo_code_id in (111, 222)
        return None, None, promo_code_id == 111

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", session_local_stub)
    monkeypatch.setattr(
        payments_reliability_async.PromoRepo,
        "get_refunded_purchase_ids_with_pending_redemption_revoke",
        _get_purchase_ids,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_by_id_for_update",
        _get_purchase,
    )
    monkeypatch.setattr(
        payments_reliability_async.PromoRepo,
        "revoke_redemption_for_refund",
        _revoke_redemption,
    )

    result = await payments_reliability_async.run_refund_promo_rollback_async(batch_size=5)

    assert result == {
        "examined": 5,
        "rolled_back": 1,
        "skipped": 3,
        "missing": 1,
        "errors": 0,
    }


@pytest.mark.asyncio
async def test_run_refund_promo_rollback_async_counts_error_when_repo_call_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase_id = uuid4()
    session_local_stub = _SessionLocalStub()

    async def _get_purchase_ids(session: object, *, limit: int) -> list[UUID]:
        del session, limit
        return [purchase_id]

    async def _get_purchase(session: object, purchase_id: UUID) -> None:
        del session, purchase_id
        raise RuntimeError("db error")

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", session_local_stub)
    monkeypatch.setattr(
        payments_reliability_async.PromoRepo,
        "get_refunded_purchase_ids_with_pending_redemption_revoke",
        _get_purchase_ids,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_by_id_for_update",
        _get_purchase,
    )

    result = await payments_reliability_async.run_refund_promo_rollback_async(batch_size=1)

    assert result == {
        "examined": 1,
        "rolled_back": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 1,
    }


@pytest.mark.asyncio
async def test_recover_single_purchase_returns_missing_when_purchase_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase_id = uuid4()
    now_utc = datetime.now(timezone.utc)
    session_local_stub = _SessionLocalStub()

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
    session_local_stub = _SessionLocalStub()

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
    session_local_stub = _SessionLocalStub()

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
    session_local_stub = _SessionLocalStub()

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
    session_local_stub = _SessionLocalStub()
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
    session_local_stub = _SessionLocalStub()

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

    def _increment(raw_successful_payment: dict[str, object] | None) -> tuple[dict[str, object], int]:
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


@pytest.mark.asyncio
async def test_recover_paid_uncredited_async_without_alert_for_clean_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_local_stub = _SessionLocalStub()
    p1 = uuid4()
    p2 = uuid4()
    p3 = uuid4()
    candidates = [SimpleNamespace(id=p1), SimpleNamespace(id=p2), SimpleNamespace(id=p3)]

    async def _get_candidates(session: object, *, older_than_utc, limit: int) -> list[SimpleNamespace]:
        del session, older_than_utc, limit
        return candidates

    async def _recovery_result(purchase_id: UUID, *, now_utc) -> str:
        del now_utc
        return {
            p1: "credited",
            p2: "skipped",
            p3: "retryable_failure",
        }[purchase_id]

    async def _forbid_alert(*, event: str, payload: dict[str, object]) -> bool:
        del event, payload
        raise AssertionError("alerts should not be sent")

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", session_local_stub)
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_paid_uncredited_older_than",
        _get_candidates,
    )
    monkeypatch.setattr(
        payments_reliability_async,
        "_recover_single_purchase",
        _recovery_result,
    )
    monkeypatch.setattr(payments_reliability_async, "send_ops_alert", _forbid_alert)

    result = await payments_reliability_async.recover_paid_uncredited_async(
        batch_size=3,
        stale_minutes=2,
    )

    assert result == {
        "examined": 3,
        "credited": 1,
        "review": 0,
        "retryable_failure": 1,
        "skipped": 1,
        "missing": 0,
        "errors": 0,
    }


@pytest.mark.asyncio
async def test_recover_paid_uncredited_async_sends_alert_on_review_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_local_stub = _SessionLocalStub()
    p1 = uuid4()
    p2 = uuid4()
    candidates = [SimpleNamespace(id=p1), SimpleNamespace(id=p2)]
    alerts: list[dict[str, object]] = []

    async def _get_candidates(session: object, *, older_than_utc, limit: int) -> list[SimpleNamespace]:
        del session, older_than_utc, limit
        return candidates

    async def _recovery_result(purchase_id: UUID, *, now_utc) -> str:
        del now_utc
        if purchase_id == p1:
            return "credited"
        if purchase_id == p2:
            return "review"
        raise AssertionError

    async def _capture_alert(*, event: str, payload: dict[str, object]) -> bool:
        alerts.append({"event": event, "payload": payload})
        return True

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", session_local_stub)
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_paid_uncredited_older_than",
        _get_candidates,
    )
    monkeypatch.setattr(
        payments_reliability_async,
        "_recover_single_purchase",
        _recovery_result,
    )
    monkeypatch.setattr(payments_reliability_async, "send_ops_alert", _capture_alert)

    result = await payments_reliability_async.recover_paid_uncredited_async(
        batch_size=2,
        stale_minutes=2,
    )

    assert result["review"] == 1
    assert result["errors"] == 0
    assert alerts == [
        {
            "event": "payments_recovery_review_required",
            "payload": result,
        }
    ]


@pytest.mark.asyncio
async def test_recover_paid_uncredited_async_counts_errors_when_recovery_crashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_local_stub = _SessionLocalStub()
    purchase = SimpleNamespace(id=uuid4())
    alerts: list[dict[str, object]] = []

    async def _get_candidates(session: object, *, older_than_utc, limit: int) -> list[SimpleNamespace]:
        del session, older_than_utc, limit
        return [purchase]

    async def _crashing_recovery(purchase_id: UUID, *, now_utc) -> str:
        del purchase_id, now_utc
        raise RuntimeError("broken")

    async def _capture_alert(*, event: str, payload: dict[str, object]) -> bool:
        alerts.append({"event": event, "payload": payload})
        return True

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", session_local_stub)
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_paid_uncredited_older_than",
        _get_candidates,
    )
    monkeypatch.setattr(
        payments_reliability_async,
        "_recover_single_purchase",
        _crashing_recovery,
    )
    monkeypatch.setattr(payments_reliability_async, "send_ops_alert", _capture_alert)

    result = await payments_reliability_async.recover_paid_uncredited_async(batch_size=1)

    assert result == {
        "examined": 1,
        "credited": 0,
        "review": 0,
        "retryable_failure": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 1,
    }
    assert alerts == [
        {
            "event": "payments_recovery_review_required",
            "payload": result,
        }
    ]


@pytest.mark.asyncio
async def test_run_refund_promo_rollback_async_counts_error_when_revoke_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase_id = uuid4()
    session_local_stub = _SessionLocalStub()

    async def _get_purchase_ids(session: object, *, limit: int) -> list[UUID]:
        del session, limit
        return [purchase_id]

    async def _get_purchase(session: object, purchase_id: UUID) -> SimpleNamespace:
        del session
        return SimpleNamespace(
            id=purchase_id,
            status="REFUNDED",
            applied_promo_code_id=123,
        )

    async def _revoke_redemption(
        session: object,
        *,
        purchase_id: UUID,
        promo_code_id: int,
        now_utc,
    ) -> tuple[None, None, bool]:
        del session, purchase_id, promo_code_id, now_utc
        raise RuntimeError("broken")

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", session_local_stub)
    monkeypatch.setattr(
        payments_reliability_async.PromoRepo,
        "get_refunded_purchase_ids_with_pending_redemption_revoke",
        _get_purchase_ids,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_by_id_for_update",
        _get_purchase,
    )
    monkeypatch.setattr(
        payments_reliability_async.PromoRepo,
        "revoke_redemption_for_refund",
        _revoke_redemption,
    )

    result = await payments_reliability_async.run_refund_promo_rollback_async(batch_size=50)

    assert result == {
        "examined": 1,
        "rolled_back": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 1,
    }
