from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.services.production_invariants import InvariantResult
from app.workers.tasks import production_invariant_alerts
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


class _SessionLocal:
    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(object())


async def test_task_records_durable_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    async def _checks(_now_utc):
        return [
            _result(name="paid_without_entitlement", status="FAIL", severity="P1", count=1),
            _result(name="analytics_daily_stale", status="OK", severity="P2", count=0),
        ]

    async def _record(_session, **kwargs):
        calls.append(kwargs)
        return {"opened_or_updated": 1, "resolved": 1}

    monkeypatch.setattr(production_invariant_alerts, "run_database_checks", _checks)
    monkeypatch.setattr(production_invariant_alerts, "record_alerts_for_results", _record)
    monkeypatch.setattr(production_invariant_alerts, "SessionLocal", _SessionLocal())

    result = await production_invariant_alerts.run_production_invariant_alerts_async()

    assert result == {
        "checks_total": 2,
        "failed_p0_p1": 1,
        "failed_p2": 0,
        "alerts_opened_or_updated": 1,
        "alerts_resolved": 1,
    }
    recorded_results = calls[0]["results"]
    assert isinstance(recorded_results, list)
    assert len(recorded_results) == 2


def test_task_wrapper_uses_heartbeat_tracking(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _run_tracked(**kwargs):
        captured.update(kwargs)
        kwargs["awaitable"].close()
        return {"checks_total": 1}

    monkeypatch.setattr(production_invariant_alerts, "run_tracked_async_job", _run_tracked)

    assert production_invariant_alerts.run_production_invariant_alerts() == {"checks_total": 1}
    assert captured["task_name"] == production_invariant_alerts.TASK_NAME
    assert captured["schedule_key"] == production_invariant_alerts.SCHEDULE_KEY


def test_task_is_not_scheduled_on_monitored_worker() -> None:
    schedule = production_invariant_alerts.celery_app.conf.beat_schedule or {}
    assert production_invariant_alerts.TASK_NAME not in {
        entry["task"] for entry in schedule.values()
    }


async def test_monitor_runs_evaluator_before_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def _run() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"checks_total": 1}

    async def _cancel_on_sleep(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(production_invariant_alerts, "run_production_invariant_alerts_async", _run)
    monkeypatch.setattr(production_invariant_alerts.asyncio, "sleep", _cancel_on_sleep)

    with pytest.raises(asyncio.CancelledError):
        await production_invariant_alerts.run_production_invariant_monitor()

    assert calls == 1


def _result(*, name: str, status: str, severity: str, count: int) -> InvariantResult:
    return InvariantResult(
        name=name,
        status=status,
        severity=severity,
        count=count,
        description=name,
        correlation_key=name,
        safe_context={"check_name": name, "count": count},
    )
