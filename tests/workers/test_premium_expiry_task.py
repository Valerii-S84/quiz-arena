from __future__ import annotations

from collections.abc import Coroutine
from types import SimpleNamespace
from typing import Any

import pytest
from celery.exceptions import Retry

from app.core.config import Settings
from app.workers import task_heartbeat
from app.workers.tasks import premium_expiry
from tests.type_helpers import AsyncBeginContext


class _SessionLocal:
    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(object())


@pytest.mark.asyncio
async def test_expire_premium_entitlements_async_marks_expired_active_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def _count(_session, **kwargs) -> int:
        calls.append(("count", kwargs))
        return 3

    async def _expire(_session, **kwargs) -> int:
        calls.append(("expire", kwargs))
        return 2

    monkeypatch.setattr(premium_expiry, "SessionLocal", _SessionLocal())
    monkeypatch.setattr(premium_expiry.EntitlementsRepo, "count_expired_active_premium", _count)
    monkeypatch.setattr(premium_expiry.EntitlementsRepo, "expire_active_premium_before", _expire)

    result = await premium_expiry.expire_premium_entitlements_async(batch_size=2)

    assert result == {
        "expired_active_before": 3,
        "expired_total": 2,
        "expired_active_remaining": 1,
    }
    assert calls[1][1]["limit"] == 2


@pytest.mark.parametrize(("batch_size", "expected_limit"), ((0, 1), (5001, 5000)))
@pytest.mark.asyncio
async def test_expire_premium_entitlements_async_bounds_batch_size(
    monkeypatch: pytest.MonkeyPatch,
    batch_size: int,
    expected_limit: int,
) -> None:
    captured: dict[str, object] = {}

    async def _count(_session, **_kwargs) -> int:
        return 0

    async def _expire(_session, **kwargs) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(premium_expiry, "SessionLocal", _SessionLocal())
    monkeypatch.setattr(premium_expiry.EntitlementsRepo, "count_expired_active_premium", _count)
    monkeypatch.setattr(premium_expiry.EntitlementsRepo, "expire_active_premium_before", _expire)

    await premium_expiry.expire_premium_entitlements_async(batch_size=batch_size)

    assert captured["limit"] == expected_limit


def test_expire_premium_entitlements_task_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _run_tracked(
        *,
        task_name: str,
        schedule_key: str,
        awaitable: Coroutine[Any, Any, dict[str, int]],
    ) -> dict[str, int]:
        captured.update(task_name=task_name, schedule_key=schedule_key)
        awaitable.close()
        return {"expired_total": 1}

    monkeypatch.setattr(premium_expiry, "run_tracked_async_job", _run_tracked)

    result = premium_expiry.expire_premium_entitlements(batch_size=50)

    assert result == {"expired_total": 1}
    assert captured == {
        "task_name": premium_expiry.TASK_NAME,
        "schedule_key": premium_expiry.SCHEDULE_KEY,
    }


def test_premium_expiry_is_default_disabled() -> None:
    assert Settings.model_fields["premium_expiry_schedule_enabled"].default is False
    assert premium_expiry.SCHEDULE_KEY not in (premium_expiry.celery_app.conf.beat_schedule or {})


def test_premium_expiry_schedule_only_registers_when_enabled() -> None:
    app = SimpleNamespace(conf=SimpleNamespace(beat_schedule={}))

    premium_expiry.configure_premium_expiry_schedule(app, enabled=False)
    assert premium_expiry.SCHEDULE_KEY not in app.conf.beat_schedule

    premium_expiry.configure_premium_expiry_schedule(app, enabled=True)
    assert app.conf.beat_schedule[premium_expiry.SCHEDULE_KEY] == {
        "task": premium_expiry.TASK_NAME,
        "schedule": 3600.0,
        "options": {"queue": "q_normal"},
    }


def test_premium_expiry_heartbeat_registry_only_registers_when_enabled() -> None:
    disabled_rows = task_heartbeat.get_critical_task_heartbeats(
        premium_expiry_schedule_enabled=False,
    )
    enabled_rows = task_heartbeat.get_critical_task_heartbeats(
        premium_expiry_schedule_enabled=True,
    )

    assert not any(row.schedule_key == premium_expiry.SCHEDULE_KEY for row in disabled_rows)
    assert any(
        row.task_name == premium_expiry.TASK_NAME
        and row.schedule_key == premium_expiry.SCHEDULE_KEY
        and row.stale_after_seconds == 7200
        and row.severity == "P2"
        for row in enabled_rows
    )


def test_premium_expiry_heartbeat_success_preserves_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[str] = []
    expected = {"expired_active_before": 1, "expired_total": 1, "expired_active_remaining": 0}

    async def _started(_session, **_kwargs) -> None:
        writes.append("started")

    async def _success(_session, **_kwargs) -> None:
        writes.append("success")

    async def _job(*, batch_size: int) -> dict[str, int]:
        assert batch_size == 25
        return expected

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _started)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_success", _success)
    monkeypatch.setattr(premium_expiry, "expire_premium_entitlements_async", _job)

    result = premium_expiry.expire_premium_entitlements(batch_size=25)

    assert result is expected
    assert writes == ["started", "success"]


@pytest.mark.parametrize(
    "expected_error",
    (RuntimeError("failure unchanged"), Retry("retry unchanged")),
)
def test_premium_expiry_heartbeat_preserves_error_semantics(
    monkeypatch: pytest.MonkeyPatch,
    expected_error: Exception,
) -> None:
    writes: list[str] = []

    async def _started(_session, **_kwargs) -> None:
        writes.append("started")

    async def _failure(_session, **_kwargs) -> None:
        writes.append("failure")

    async def _job(*, batch_size: int) -> dict[str, int]:
        assert batch_size == 500
        raise expected_error

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _started)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_failure", _failure)
    monkeypatch.setattr(premium_expiry, "expire_premium_entitlements_async", _job)

    with pytest.raises(type(expected_error)) as raised:
        premium_expiry.expire_premium_entitlements()

    assert raised.value is expected_error
    assert writes == ["started", "failure"]


def test_premium_expiry_ignores_heartbeat_persistence_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {"expired_active_before": 1, "expired_total": 1, "expired_active_remaining": 0}

    async def _write_failure(_session, **_kwargs) -> None:
        raise RuntimeError("heartbeat unavailable")

    async def _job(*, batch_size: int) -> dict[str, int]:
        assert batch_size == 500
        return expected

    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_started", _write_failure)
    monkeypatch.setattr(task_heartbeat.WorkerTaskHeartbeatsRepo, "record_success", _write_failure)
    monkeypatch.setattr(task_heartbeat.logger, "warning", lambda _event, **_kwargs: None)
    monkeypatch.setattr(premium_expiry, "expire_premium_entitlements_async", _job)

    assert premium_expiry.expire_premium_entitlements() is expected
