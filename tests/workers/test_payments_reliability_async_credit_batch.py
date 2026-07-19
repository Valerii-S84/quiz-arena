from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.workers.tasks import payments_reliability_async
from tests.workers.payments_reliability_async_support import SessionLocalStub


def _patch_recovery_candidates(
    monkeypatch: pytest.MonkeyPatch,
    candidates: list[SimpleNamespace],
) -> None:
    async def _get_candidates(
        session: object, *, older_than_utc, limit: int
    ) -> list[SimpleNamespace]:
        del session, older_than_utc, limit
        return candidates

    monkeypatch.setattr(payments_reliability_async, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_paid_uncredited_older_than",
        _get_candidates,
    )


def _patch_recovery_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: dict[UUID, str],
) -> None:
    async def _recovery_result(purchase_id: UUID, *, now_utc) -> str:
        del now_utc
        return outcomes[purchase_id]

    monkeypatch.setattr(
        payments_reliability_async,
        "_recover_single_purchase",
        _recovery_result,
    )


def _patch_alert_capture(
    monkeypatch: pytest.MonkeyPatch,
    alerts: list[dict[str, object]],
) -> None:
    async def _capture_alert(*, event: str, payload: dict[str, object]) -> bool:
        alerts.append({"event": event, "payload": payload})
        return True

    monkeypatch.setattr(payments_reliability_async, "send_ops_alert", _capture_alert)


def _patch_recovery_log_capture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    infos: list[dict[str, object]] | None = None,
    warnings: list[dict[str, object]] | None = None,
) -> None:
    if infos is not None:
        monkeypatch.setattr(
            payments_reliability_async.logger,
            "info",
            lambda event, **kwargs: infos.append({"event": event, **kwargs}),
        )
    if warnings is not None:
        monkeypatch.setattr(
            payments_reliability_async.logger,
            "warning",
            lambda event, **kwargs: warnings.append({"event": event, **kwargs}),
        )


@pytest.mark.asyncio
async def test_recover_paid_uncredited_async_without_alert_for_clean_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p1 = uuid4()
    p2 = uuid4()
    p3 = uuid4()
    candidates = [SimpleNamespace(id=p1), SimpleNamespace(id=p2), SimpleNamespace(id=p3)]
    infos: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []

    async def _forbid_alert(*, event: str, payload: dict[str, object]) -> bool:
        del event, payload
        raise AssertionError("alerts should not be sent")

    _patch_recovery_candidates(monkeypatch, candidates)
    _patch_recovery_outcomes(
        monkeypatch,
        {p1: "credited", p2: "skipped", p3: "retryable_failure"},
    )
    monkeypatch.setattr(payments_reliability_async, "send_ops_alert", _forbid_alert)
    _patch_recovery_log_capture(monkeypatch, infos=infos, warnings=warnings)

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
    assert infos[0] == {
        "event": "payment_recovery_started",
        "batch_size": 3,
        "stale_minutes": 2,
    }
    assert infos[-2]["event"] == "payment_recovery_finished"
    assert warnings == [
        {
            "event": "payment_recovery_failed",
            "purchase_id": str(p3),
            "outcome": "retryable_failure",
        }
    ]


@pytest.mark.asyncio
async def test_recover_paid_uncredited_async_sends_alert_on_review_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p1 = uuid4()
    p2 = uuid4()
    candidates = [SimpleNamespace(id=p1), SimpleNamespace(id=p2)]
    alerts: list[dict[str, object]] = []

    _patch_recovery_candidates(monkeypatch, candidates)
    _patch_recovery_outcomes(monkeypatch, {p1: "credited", p2: "review"})
    _patch_alert_capture(monkeypatch, alerts)

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
    purchase = SimpleNamespace(id=uuid4())
    alerts: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []

    async def _crashing_recovery(purchase_id: UUID, *, now_utc) -> str:
        del purchase_id, now_utc
        raise RuntimeError("broken")

    _patch_recovery_candidates(monkeypatch, [purchase])
    monkeypatch.setattr(
        payments_reliability_async,
        "_recover_single_purchase",
        _crashing_recovery,
    )
    _patch_alert_capture(monkeypatch, alerts)
    _patch_recovery_log_capture(monkeypatch, warnings=warnings)

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
    assert warnings == [
        {
            "event": "payment_recovery_failed",
            "purchase_id": str(purchase.id),
            "outcome": "error",
            "error_type": "RuntimeError",
        }
    ]
