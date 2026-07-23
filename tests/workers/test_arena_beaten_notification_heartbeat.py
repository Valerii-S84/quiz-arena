from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.game.arena_duels.constants import ARENA_BEATEN_NOTIFICATION_TYPE
from app.game.arena_duels.types import ArenaBeatenNotification
from app.workers import task_heartbeat
from app.workers.tasks import arena_duels
from app.workers.tasks.arena_duels_notification_payload import notification_payload


class _FailingContext:
    async def __aenter__(self) -> object:
        raise RuntimeError("heartbeat persistence unavailable")

    async def __aexit__(self, *_args: object) -> None:
        return None


class _FailingSessionLocal:
    def begin(self) -> _FailingContext:
        return _FailingContext()


def _notification() -> ArenaBeatenNotification:
    return ArenaBeatenNotification(
        arena_duel_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        previous_best_attempt_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        previous_best_user_id=11,
        previous_best_score=6,
        previous_best_time_ms=48_000,
        new_best_attempt_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        new_best_user_id=22,
        new_best_score=7,
        new_best_time_ms=52_000,
        notification_type=ARENA_BEATEN_NOTIFICATION_TYPE,
    )


def test_arena_notification_heartbeat_is_fail_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracked: list[tuple[str, str]] = []
    warnings: list[str] = []
    expected = {"sent_total": 1, "failed_total": 0, "skipped_total": 0}

    async def _send_notification(**_kwargs: object) -> dict[str, int]:
        return expected

    def _run_tracked(*, task_name: str, schedule_key: str, awaitable):
        tracked.append((task_name, schedule_key))
        return asyncio.run(
            task_heartbeat.run_with_task_heartbeat(
                task_name=task_name,
                schedule_key=schedule_key,
                awaitable=awaitable,
                session_local=_FailingSessionLocal(),
            )
        )

    monkeypatch.setattr(arena_duels, "send_arena_beaten_notification", _send_notification)
    monkeypatch.setattr(arena_duels, "run_tracked_async_job", _run_tracked)
    monkeypatch.setattr(
        task_heartbeat.logger,
        "warning",
        lambda event, **_kwargs: warnings.append(event),
    )

    result = arena_duels.send_arena_beaten_notification_task(
        notification_payload(_notification()),
        datetime(2026, 7, 23, 12, 0, tzinfo=UTC).isoformat(),
    )

    assert result == expected
    assert tracked == [
        (
            "app.workers.tasks.arena_duels.send_arena_beaten_notification_task",
            "arena-beaten-notification-on-demand",
        )
    ]
    assert warnings == [
        "worker_task_heartbeat_start_write_failed",
        "worker_task_heartbeat_success_write_failed",
    ]
