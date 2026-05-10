from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.workers.tasks import telegram_updates


class _RetryRaised(Exception):
    pass


class _TaskSelf:
    def __init__(self, retries: int) -> None:
        self.request = SimpleNamespace(id="task-1", retries=retries)
        self.retry_kwargs: dict[str, object] | None = None

    def retry(self, **kwargs):
        self.retry_kwargs = kwargs
        raise _RetryRaised


async def _process_update(_payload, **_kwargs):
    return "processed"


async def _event(**_kwargs):
    return None


def test_process_telegram_update_schedules_retry_and_records_event(monkeypatch) -> None:
    task_self = _TaskSelf(retries=1)
    task = telegram_updates.process_telegram_update._get_current_object()
    events: list[str] = []

    def _run(coro):
        name = coro.cr_code.co_name
        coro.close()
        if name == "_process_update":
            raise RuntimeError("boom")
        events.append(name)
        return None

    monkeypatch.setattr(telegram_updates, "process_update_async", _process_update)
    monkeypatch.setattr(telegram_updates, "_emit_reliability_event", _event)
    monkeypatch.setattr(telegram_updates, "run_async_job", _run)
    monkeypatch.setattr(telegram_updates, "_retry_backoff_seconds", lambda **_kwargs: 9)
    monkeypatch.setattr(task, "retry", task_self.retry)

    task.push_request(id="task-1", retries=1)
    try:
        with pytest.raises(_RetryRaised):
            telegram_updates.process_telegram_update(update_payload={"update_id": 7})
    finally:
        task.pop_request()

    assert task_self.retry_kwargs is not None
    assert task_self.retry_kwargs["countdown"] == 9
    assert events == ["_event"]


def test_process_telegram_update_final_failure_records_event_and_reraises(monkeypatch) -> None:
    task = telegram_updates.process_telegram_update._get_current_object()
    events: list[str] = []

    def _run(coro):
        name = coro.cr_code.co_name
        coro.close()
        if name == "_process_update":
            raise RuntimeError("boom")
        events.append(name)
        return None

    monkeypatch.setattr(telegram_updates, "process_update_async", _process_update)
    monkeypatch.setattr(telegram_updates, "_emit_reliability_event", _event)
    monkeypatch.setattr(telegram_updates, "run_async_job", _run)

    task.push_request(id="task-1", retries=telegram_updates.TASK_MAX_RETRIES)
    try:
        with pytest.raises(RuntimeError):
            telegram_updates.process_telegram_update(update_payload={"update_id": 7})
    finally:
        task.pop_request()

    assert events == ["_event"]
