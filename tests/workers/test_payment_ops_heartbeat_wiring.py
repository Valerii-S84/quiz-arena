from __future__ import annotations

from collections.abc import Callable, Coroutine
from types import ModuleType
from typing import Any

import pytest
from celery.exceptions import Retry

from app.workers import task_heartbeat
from app.workers.tasks import analytics_daily, payments_reliability


@pytest.mark.parametrize(
    ("task_module", "task", "task_name", "schedule_key"),
    (
        (
            payments_reliability,
            payments_reliability.recover_paid_uncredited,
            "app.workers.tasks.payments_reliability.recover_paid_uncredited",
            "recover-paid-uncredited-every-5-minutes",
        ),
        (
            payments_reliability,
            payments_reliability.run_payment_invariant_alerts,
            "app.workers.tasks.payments_reliability.run_payment_invariant_alerts",
            "payment-invariant-alerts-every-minute",
        ),
        (
            payments_reliability,
            payments_reliability.expire_stale_unpaid_invoices,
            "app.workers.tasks.payments_reliability.expire_stale_unpaid_invoices",
            "expire-stale-unpaid-invoices-every-5-minutes",
        ),
        (
            payments_reliability,
            payments_reliability.run_refund_promo_rollback,
            "app.workers.tasks.payments_reliability.run_refund_promo_rollback",
            "refund-promo-rollback-every-5-minutes",
        ),
        (
            payments_reliability,
            payments_reliability.run_payments_reconciliation,
            "app.workers.tasks.payments_reliability.run_payments_reconciliation",
            "payments-reconciliation-every-15-minutes",
        ),
        (
            payments_reliability,
            payments_reliability.run_telegram_stars_reconciliation,
            "app.workers.tasks.payments_reliability.run_telegram_stars_reconciliation",
            "telegram-stars-reconciliation-every-5-minutes",
        ),
        (
            analytics_daily,
            analytics_daily.run_analytics_daily_aggregation,
            "app.workers.tasks.analytics_daily.run_analytics_daily_aggregation",
            "analytics-daily-aggregation-hourly",
        ),
    ),
)
def test_registered_task_entrypoint_uses_heartbeat_identity(
    monkeypatch: pytest.MonkeyPatch,
    task_module: ModuleType,
    task: Callable[[], object],
    task_name: str,
    schedule_key: str,
) -> None:
    captured: dict[str, str] = {}
    result_marker = object()

    def _tracked(
        *,
        task_name: str,
        schedule_key: str,
        awaitable: Coroutine[Any, Any, object],
    ) -> object:
        captured.update(task_name=task_name, schedule_key=schedule_key)
        awaitable.close()
        return result_marker

    monkeypatch.setattr(task_module, "run_tracked_async_job", _tracked)

    assert task() is result_marker
    assert captured == {"task_name": task_name, "schedule_key": schedule_key}
    assert (task_name, schedule_key) in {
        (row.task_name, row.schedule_key) for row in task_heartbeat.get_critical_task_heartbeats()
    }


def test_payment_heartbeat_success_preserves_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[str] = []

    async def _started(_session, **_kwargs) -> None:
        writes.append("started")

    async def _success(_session, **_kwargs) -> None:
        writes.append("success")

    expected = {
        "examined": 7,
        "credited": 5,
        "review": 0,
        "retryable_failure": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 0,
    }

    async def _job(*, batch_size: int, stale_minutes: int) -> dict[str, int]:
        assert (batch_size, stale_minutes) == (7, 5)
        return expected

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _started)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_success", _success)
    monkeypatch.setattr(payments_reliability, "recover_paid_uncredited_async", _job)

    result = payments_reliability.recover_paid_uncredited(batch_size=7, stale_minutes=5)

    assert result is expected
    assert writes == ["started", "success"]


def test_payment_heartbeat_failure_preserves_retry_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[str] = []
    expected_error = Retry("retry unchanged")

    async def _started(_session, **_kwargs) -> None:
        writes.append("started")

    async def _failure(_session, **_kwargs) -> None:
        writes.append("failure")

    async def _job(*, stale_minutes: int) -> dict[str, int]:
        assert stale_minutes == 45
        raise expected_error

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _started)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_failure", _failure)
    monkeypatch.setattr(payments_reliability, "expire_stale_unpaid_invoices_async", _job)

    with pytest.raises(Retry) as raised:
        payments_reliability.expire_stale_unpaid_invoices(stale_minutes=45)

    assert raised.value is expected_error
    assert writes == ["started", "failure"]


def test_ops_task_ignores_heartbeat_persistence_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _write_failure(_session, **_kwargs) -> None:
        raise RuntimeError("heartbeat unavailable")

    expected = {"days_processed": 1, "local_days_berlin": ["2026-07-22"]}

    async def _job(*, days_back: int) -> dict[str, object]:
        assert days_back == 1
        return expected

    monkeypatch.setattr(
        task_heartbeat.WorkerTaskHeartbeatsRepo,
        "record_started",
        _write_failure,
    )
    monkeypatch.setattr(
        task_heartbeat.WorkerTaskHeartbeatsRepo,
        "record_success",
        _write_failure,
    )
    monkeypatch.setattr(task_heartbeat.logger, "warning", lambda _event, **_kwargs: None)
    monkeypatch.setattr(analytics_daily, "run_analytics_daily_aggregation_async", _job)

    result = analytics_daily.run_analytics_daily_aggregation(days_back=1)

    assert result is expected
