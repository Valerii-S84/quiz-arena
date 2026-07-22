from __future__ import annotations

from typing import cast

import pytest

from app.workers import task_heartbeat
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


def test_critical_task_heartbeat_registry_is_unique_and_periodic() -> None:
    rows = task_heartbeat.get_critical_task_heartbeats()
    identities = {(row.task_name, row.schedule_key) for row in rows}

    assert rows
    assert len(identities) == len(rows)
    assert all(row.stale_after_seconds > 0 for row in rows)
    assert {row.severity for row in rows} <= {"P1", "P2"}
    assert not any("premium_expiry" in row.task_name for row in rows)
