from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from app.workers import task_heartbeat
from app.workers.tasks import (
    analytics_daily,
    arena_duels_schedule,
    daily_cup_schedule,
    offers_observability,
    payments_reliability_schedule,
    telegram_updates_observability,
    tournaments_schedule,
)
from tests.type_helpers import AsyncBeginContext


class _SessionLocal:
    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(object())


@pytest.mark.asyncio
async def test_run_with_task_heartbeat_records_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def _started(_session, **kwargs) -> None:
        calls.append(("started", kwargs))

    async def _success(_session, **kwargs) -> None:
        calls.append(("success", kwargs))

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _started)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_success", _success)

    async def _job() -> dict[str, int]:
        return {"processed": 1}

    result = await task_heartbeat.run_with_task_heartbeat(
        task_name="task",
        schedule_key="schedule",
        awaitable=_job(),
        session_local=_SessionLocal(),
    )

    assert result == {"processed": 1}
    assert [name for name, _payload in calls] == ["started", "success"]
    assert calls[1][1]["started_at"] == calls[0][1]["started_at"]
    assert cast(int, calls[1][1]["duration_ms"]) >= 0


@pytest.mark.asyncio
async def test_run_with_task_heartbeat_records_failure_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def _started(_session, **kwargs) -> None:
        calls.append(("started", kwargs))

    async def _failure(_session, **kwargs) -> None:
        calls.append(("failure", kwargs))

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _started)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_failure", _failure)

    async def _job() -> None:
        raise RuntimeError("task failed")

    with pytest.raises(RuntimeError, match="task failed"):
        await task_heartbeat.run_with_task_heartbeat(
            task_name="task",
            schedule_key="schedule",
            awaitable=_job(),
            session_local=_SessionLocal(),
        )

    assert [name for name, _payload in calls] == ["started", "failure"]
    assert calls[1][1]["started_at"] == calls[0][1]["started_at"]
    error_hash = cast(str, calls[1][1]["error_hash"])
    assert len(error_hash) == 64
    assert "task failed" not in error_hash


@pytest.mark.asyncio
async def test_heartbeat_write_failure_does_not_fail_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[str] = []

    async def _write_failure(_session, **_kwargs) -> None:
        raise RuntimeError("heartbeat unavailable")

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _write_failure)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_success", _write_failure)
    monkeypatch.setattr(
        task_heartbeat.logger,
        "warning",
        lambda event, **_kwargs: warnings.append(event),
    )

    async def _job() -> str:
        return "ok"

    result = await task_heartbeat.run_with_task_heartbeat(
        task_name="task",
        schedule_key="schedule",
        awaitable=_job(),
        session_local=_SessionLocal(),
    )

    assert result == "ok"
    assert warnings == [
        "worker_task_heartbeat_start_write_failed",
        "worker_task_heartbeat_success_write_failed",
    ]


def test_critical_task_heartbeat_registry_is_unique_and_valid() -> None:
    rows = task_heartbeat.get_critical_task_heartbeats()
    identities = {(row.task_name, row.schedule_key) for row in rows}

    assert rows
    assert len(identities) == len(rows)
    assert all(row.stale_after_seconds is None or row.stale_after_seconds > 0 for row in rows)
    assert {row.severity for row in rows} <= {"P1", "P2"}
    assert not any("premium_expiry" in row.task_name for row in rows)


def test_critical_task_heartbeat_registry_entry_accepts_on_demand_staleness() -> None:
    row = task_heartbeat.CriticalTaskHeartbeat(
        task_name="app.workers.tasks.example.run_on_demand",
        schedule_key="example-on-demand",
        stale_after_seconds=None,
    )

    assert row.stale_after_seconds is None


def test_critical_task_heartbeat_registry_entry_accepts_numeric_staleness() -> None:
    row = task_heartbeat.CriticalTaskHeartbeat(
        task_name="app.workers.tasks.example.run_periodic",
        schedule_key="example-every-5-minutes",
        stale_after_seconds=600,
    )

    assert row.stale_after_seconds == 600


def test_payment_reconciliation_has_no_unreachable_registry_duplicate() -> None:
    rows = [
        row
        for row in task_heartbeat.get_critical_task_heartbeats()
        if row.task_name == "app.workers.tasks.payments_reliability.run_payments_reconciliation"
    ]

    assert [(row.schedule_key, row.stale_after_seconds) for row in rows] == [
        ("payments-reconciliation-every-15-minutes", 1800)
    ]


@pytest.mark.parametrize(
    ("task_name", "schedule_key", "stale_after_seconds", "severity"),
    (
        (
            "app.workers.tasks.telegram_updates_observability."
            "run_telegram_updates_reliability_alerts",
            "telegram-updates-reliability-alerts-every-5-minutes",
            600,
            "P1",
        ),
        (
            "app.workers.tasks.payments_reliability.run_payment_invariant_alerts",
            "payment-invariant-alerts-every-minute",
            120,
            "P1",
        ),
        (
            "app.workers.tasks.tournaments_messaging." "run_private_tournament_round_messaging",
            "private-tournament-round-messaging-on-demand",
            None,
            "P1",
        ),
        (
            "app.workers.tasks.arena_duels.send_arena_beaten_notification_task",
            "arena-beaten-notification-on-demand",
            None,
            "P1",
        ),
        (
            "app.workers.tasks.offers_observability.run_offers_funnel_alerts",
            "offers-funnel-alerts-every-15-minutes",
            1800,
            "P2",
        ),
    ),
)
def test_remaining_observability_registry_entries(
    task_name: str,
    schedule_key: str,
    stale_after_seconds: int | None,
    severity: str,
) -> None:
    rows = task_heartbeat.get_critical_task_heartbeats()

    assert (
        task_heartbeat.CriticalTaskHeartbeat(
            task_name=task_name,
            schedule_key=schedule_key,
            stale_after_seconds=stale_after_seconds,
            severity=severity,
        )
        in rows
    )


def test_daily_cup_heartbeat_registry_entries_match_source_identities() -> None:
    expected = {
        (
            "app.workers.tasks.daily_cup.send_invite",
            "daily-cup-send-invite-on-demand",
            None,
            "P1",
        ),
        (
            "app.workers.tasks.daily_cup.send_invite_registration",
            "daily-cup-send-invite-registration",
            172800,
            "P1",
        ),
        (
            "app.workers.tasks.daily_cup.open_registration",
            "daily-cup-open-registration",
            None,
            "P1",
        ),
        (
            "app.workers.tasks.daily_cup.send_last_call_reminder",
            "daily-cup-last-call-reminder",
            172800,
            "P1",
        ),
        (
            "app.workers.tasks.daily_cup.send_prestart_reminder",
            "daily-cup-prestart-reminder",
            172800,
            "P1",
        ),
        (
            "app.workers.tasks.daily_cup.send_turn_reminders",
            "daily-cup-turn-reminders",
            1200,
            "P1",
        ),
        (
            "app.workers.tasks.daily_cup.close_registration_and_start",
            "daily-cup-close-registration",
            172800,
            "P1",
        ),
        (
            "app.workers.tasks.daily_cup.publish_final_results",
            "daily-cup-publish-final-results",
            172800,
            "P1",
        ),
        (
            "app.workers.tasks.daily_cup.advance_rounds",
            "daily-cup-round-advance",
            120,
            "P1",
        ),
        (
            "app.workers.tasks.daily_cup.run_daily_cup_round_messaging",
            "daily-cup-round-messaging-on-demand",
            None,
            "P1",
        ),
    }
    actual = {
        (row.task_name, row.schedule_key, row.stale_after_seconds, row.severity)
        for row in task_heartbeat.get_critical_task_heartbeats()
        if row.task_name.startswith("app.workers.tasks.daily_cup.")
    }

    assert actual == expected


def test_periodic_heartbeat_registry_entries_match_current_schedule() -> None:
    app = SimpleNamespace(conf=SimpleNamespace(beat_schedule={}))
    payments_reliability_schedule.configure_payments_reliability_schedule(app)
    arena_duels_schedule.configure_arena_duels_schedule(app)
    daily_cup_schedule.configure_daily_cup_schedule(app)
    tournaments_schedule.configure_private_tournaments_schedule(app)

    for task_module, schedule_key in (
        (analytics_daily, "analytics-daily-aggregation-hourly"),
        (offers_observability, "offers-funnel-alerts-every-15-minutes"),
        (
            telegram_updates_observability,
            "telegram-updates-reliability-alerts-every-5-minutes",
        ),
    ):
        module_schedule = task_module.celery_app.conf.beat_schedule or {}
        app.conf.beat_schedule[schedule_key] = module_schedule[schedule_key]

    for row in task_heartbeat.get_critical_task_heartbeats():
        if row.stale_after_seconds is None:
            continue
        schedule_entry = app.conf.beat_schedule[row.schedule_key]
        assert schedule_entry["task"] == row.task_name
