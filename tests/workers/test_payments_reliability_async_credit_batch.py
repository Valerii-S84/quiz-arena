from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.workers.tasks import payments_reliability_async
from tests.workers.payments_reliability_async_support import SessionLocalStub


@pytest.mark.asyncio
async def test_recover_paid_uncredited_async_without_alert_for_clean_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_local_stub = SessionLocalStub()
    p1 = uuid4()
    p2 = uuid4()
    p3 = uuid4()
    candidates = [SimpleNamespace(id=p1), SimpleNamespace(id=p2), SimpleNamespace(id=p3)]

    async def _get_candidates(
        session: object, *, older_than_utc, limit: int
    ) -> list[SimpleNamespace]:
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
    session_local_stub = SessionLocalStub()
    p1 = uuid4()
    p2 = uuid4()
    candidates = [SimpleNamespace(id=p1), SimpleNamespace(id=p2)]
    alerts: list[dict[str, object]] = []

    async def _get_candidates(
        session: object, *, older_than_utc, limit: int
    ) -> list[SimpleNamespace]:
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
    session_local_stub = SessionLocalStub()
    purchase = SimpleNamespace(id=uuid4())
    alerts: list[dict[str, object]] = []

    async def _get_candidates(
        session: object, *, older_than_utc, limit: int
    ) -> list[SimpleNamespace]:
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
