from __future__ import annotations

from typing import cast

import pytest

from app.workers import task_heartbeat
from tests.type_helpers import AsyncBeginContext


class _SessionLocal:
    def __init__(self) -> None:
        self.sessions: list[object] = []

    def begin(self) -> AsyncBeginContext[object]:
        session = object()
        self.sessions.append(session)
        return AsyncBeginContext(session)


@pytest.mark.asyncio
async def test_run_with_task_heartbeat_records_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    session_local = _SessionLocal()

    async def _started(_session, **kwargs) -> None:
        calls.append(("started", kwargs))

    async def _success(_session, **kwargs) -> None:
        calls.append(("success", kwargs))

    async def _failure(_session, **kwargs) -> None:
        calls.append(("failure", kwargs))

    async def _job() -> dict[str, int]:
        return {"processed": 1}

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _started)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_success", _success)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_failure", _failure)

    result = await task_heartbeat.run_with_task_heartbeat(
        task_name="task",
        schedule_key="schedule",
        awaitable=_job(),
        session_local=session_local,
    )

    assert result == {"processed": 1}
    assert [name for name, _payload in calls] == ["started", "success"]
    assert cast(int, calls[1][1]["duration_ms"]) >= 0


@pytest.mark.asyncio
async def test_run_with_task_heartbeat_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    session_local = _SessionLocal()

    async def _started(_session, **kwargs) -> None:
        calls.append(("started", kwargs))

    async def _success(_session, **kwargs) -> None:
        calls.append(("success", kwargs))

    async def _failure(_session, **kwargs) -> None:
        calls.append(("failure", kwargs))

    async def _job() -> None:
        raise RuntimeError("task failed")

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _started)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_success", _success)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_failure", _failure)

    with pytest.raises(RuntimeError):
        await task_heartbeat.run_with_task_heartbeat(
            task_name="task",
            schedule_key="schedule",
            awaitable=_job(),
            session_local=session_local,
        )

    assert [name for name, _payload in calls] == ["started", "failure"]
    assert "error_hash" in calls[1][1]


@pytest.mark.asyncio
async def test_heartbeat_write_failure_does_not_fail_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[tuple[str, dict[str, object]]] = []

    async def _started(_session, **_kwargs) -> None:
        raise RuntimeError("heartbeat unavailable")

    async def _success(_session, **_kwargs) -> None:
        raise RuntimeError("heartbeat unavailable")

    async def _job() -> str:
        return "ok"

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _started)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_success", _success)
    monkeypatch.setattr(
        task_heartbeat.logger,
        "warning",
        lambda event, **kwargs: warnings.append((event, kwargs)),
    )

    result = await task_heartbeat.run_with_task_heartbeat(
        task_name="task",
        schedule_key="schedule",
        awaitable=_job(),
        session_local=_SessionLocal(),
    )

    assert result == "ok"
    assert {event for event, _kwargs in warnings} == {
        "worker_task_heartbeat_start_write_failed",
        "worker_task_heartbeat_success_write_failed",
    }


def test_critical_task_heartbeat_registry_marks_on_demand_without_stale_alert() -> None:
    rows = task_heartbeat.get_critical_task_heartbeats()

    assert any(
        row.task_name == "app.workers.tasks.arena_duels.send_arena_beaten_notification_task"
        and row.stale_after_seconds is None
        for row in rows
    )
    assert any(
        row.schedule_key == "payment-invariant-alerts-every-minute"
        and row.stale_after_seconds == 120
        and row.severity == "P1"
        for row in rows
    )
