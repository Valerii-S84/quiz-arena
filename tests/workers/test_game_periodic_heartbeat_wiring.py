from __future__ import annotations

from collections.abc import Callable, Coroutine
from types import ModuleType
from typing import Any

import pytest
from celery.exceptions import Retry

from app.workers import task_heartbeat
from app.workers.tasks import arena_duels, tournaments


def test_game_periodic_tasks_have_exact_registry_configuration() -> None:
    expected = {
        "app.workers.tasks.arena_duels.expire_arena_duels": (
            "arena-duel-expiry-every-5-minutes",
            600,
            "P2",
        ),
        "app.workers.tasks.tournaments.run_private_tournament_rounds": (
            "private-tournaments-round-lifecycle",
            600,
            "P1",
        ),
    }
    actual = {
        row.task_name: (row.schedule_key, row.stale_after_seconds, row.severity)
        for row in task_heartbeat.get_critical_task_heartbeats()
        if row.task_name in expected
    }

    assert actual == expected


@pytest.mark.parametrize(
    ("task_module", "task", "task_name", "schedule_key"),
    (
        (
            arena_duels,
            arena_duels.expire_arena_duels_task,
            "app.workers.tasks.arena_duels.expire_arena_duels",
            "arena-duel-expiry-every-5-minutes",
        ),
        (
            tournaments,
            tournaments.run_private_tournament_rounds,
            "app.workers.tasks.tournaments.run_private_tournament_rounds",
            "private-tournaments-round-lifecycle",
        ),
    ),
)
def test_game_periodic_task_uses_exact_heartbeat_identity(
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


def test_game_periodic_heartbeat_success_preserves_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[str] = []
    expected = {"expired_active_total": 2, "expired_draft_total": 1}

    async def _started(_session, **_kwargs) -> None:
        writes.append("started")

    async def _success(_session, **_kwargs) -> None:
        writes.append("success")

    async def _job() -> dict[str, int]:
        return expected

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _started)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_success", _success)
    monkeypatch.setattr(arena_duels, "expire_arena_duels", _job)

    result = arena_duels.expire_arena_duels_task()

    assert result is expected
    assert writes == ["started", "success"]


def test_game_periodic_heartbeat_failure_preserves_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[str] = []
    expected_error = RuntimeError("task failure unchanged")

    async def _started(_session, **_kwargs) -> None:
        writes.append("started")

    async def _failure(_session, **_kwargs) -> None:
        writes.append("failure")

    async def _job(*, batch_size: int, round_duration_hours: int) -> dict[str, int]:
        assert (batch_size, round_duration_hours) == (7, 12)
        raise expected_error

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _started)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_failure", _failure)
    monkeypatch.setattr(tournaments, "run_private_tournament_rounds_async", _job)

    with pytest.raises(RuntimeError) as raised:
        tournaments.run_private_tournament_rounds(batch_size=7, round_duration_hours=12)

    assert raised.value is expected_error
    assert writes == ["started", "failure"]


def test_game_periodic_heartbeat_preserves_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[str] = []
    expected_error = Retry("retry unchanged")

    async def _started(_session, **_kwargs) -> None:
        writes.append("started")

    async def _failure(_session, **_kwargs) -> None:
        writes.append("failure")

    async def _job(*, batch_size: int, round_duration_hours: int) -> dict[str, int]:
        del batch_size, round_duration_hours
        raise expected_error

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _started)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_failure", _failure)
    monkeypatch.setattr(tournaments, "run_private_tournament_rounds_async", _job)

    with pytest.raises(Retry) as raised:
        tournaments.run_private_tournament_rounds()

    assert raised.value is expected_error
    assert writes == ["started", "failure"]


def test_game_periodic_task_ignores_heartbeat_persistence_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {"expired_active_total": 3, "expired_draft_total": 2}

    async def _write_failure(_session, **_kwargs) -> None:
        raise RuntimeError("heartbeat unavailable")

    async def _job() -> dict[str, int]:
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
    monkeypatch.setattr(arena_duels, "expire_arena_duels", _job)

    result = arena_duels.expire_arena_duels_task()

    assert result is expected
