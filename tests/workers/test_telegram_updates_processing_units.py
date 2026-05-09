from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.workers.tasks import telegram_updates_processing as processing
from app.workers.tasks.telegram_updates_config import (
    _ACQUIRE_CREATED,
    _ACQUIRE_DUPLICATE,
    _ACQUIRE_RECLAIMED_FAILED,
    _ACQUIRE_RECLAIMED_STALE,
)
from tests.workers.payments_reliability_async_support import SessionLocalStub


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("created", "failed", "stale", "expected"),
    [
        (True, False, False, _ACQUIRE_CREATED),
        (False, True, False, _ACQUIRE_RECLAIMED_FAILED),
        (False, False, True, _ACQUIRE_RECLAIMED_STALE),
        (False, False, False, _ACQUIRE_DUPLICATE),
    ],
)
async def test_acquire_processing_slot_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    created: bool,
    failed: bool,
    stale: bool,
    expected: str,
) -> None:
    monkeypatch.setattr(processing, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        processing.ProcessedUpdatesRepo,
        "try_create_processing_slot",
        _async_return(created),
    )
    monkeypatch.setattr(
        processing.ProcessedUpdatesRepo,
        "try_reclaim_failed_processing_slot",
        _async_return(failed),
    )
    monkeypatch.setattr(
        processing.ProcessedUpdatesRepo,
        "try_reclaim_stale_processing_slot",
        _async_return(stale),
    )

    assert (
        await processing._acquire_processing_slot(
            100,
            task_id="task-1",
            processing_ttl_seconds=30,
        )
        == expected
    )


@pytest.mark.asyncio
async def test_process_update_duplicate_returns_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(processing, "_acquire_processing_slot", _async_return(_ACQUIRE_DUPLICATE))

    assert await processing.process_update_async({}, update_id=100, task_id="task-1") == "duplicate"


@pytest.mark.asyncio
async def test_process_update_success_marks_processed(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses: list[dict[str, object]] = []
    bot = SimpleNamespace(session=SimpleNamespace(close=_async_return(None)))
    dispatcher = SimpleNamespace(feed_update=_async_return(None))
    monkeypatch.setattr(processing, "_acquire_processing_slot", _async_return(_ACQUIRE_CREATED))
    monkeypatch.setattr(processing, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(processing.Update, "model_validate", lambda payload: payload)
    _patch_telegram_task_factories(monkeypatch, bot=bot, dispatcher=dispatcher)

    async def _set_status(_session, **kwargs) -> None:
        statuses.append(kwargs)

    monkeypatch.setattr(processing.ProcessedUpdatesRepo, "set_status", _set_status)

    assert await processing.process_update_async({"update_id": 100}, update_id=100) == "processed"
    assert statuses == [{"update_id": 100, "status": "PROCESSED", "processing_task_id": None}]


@pytest.mark.asyncio
async def test_process_update_reclaimed_stale_emits_reliability_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, Any]] = []
    bot = SimpleNamespace(session=SimpleNamespace(close=_async_return(None)))
    dispatcher = SimpleNamespace(feed_update=_async_return(None))
    monkeypatch.setattr(
        processing,
        "_acquire_processing_slot",
        _async_return(_ACQUIRE_RECLAIMED_STALE),
    )
    monkeypatch.setattr(processing, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(processing.Update, "model_validate", lambda payload: payload)
    monkeypatch.setattr(processing, "emit_reliability_event", _append_kwargs(events))
    monkeypatch.setattr(processing.ProcessedUpdatesRepo, "set_status", _async_return(None))
    _patch_telegram_task_factories(monkeypatch, bot=bot, dispatcher=dispatcher)

    assert await processing.process_update_async({}, update_id=100, task_id="task-1") == "processed"
    assert events[0]["payload"]["task_id"] == "task-1"


def _patch_telegram_task_factories(monkeypatch: pytest.MonkeyPatch, *, bot, dispatcher) -> None:
    from app.workers.tasks import telegram_updates

    monkeypatch.setattr(telegram_updates, "build_bot", lambda: bot)
    monkeypatch.setattr(telegram_updates, "build_dispatcher", lambda: dispatcher)


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _append_kwargs(target: list[dict[str, Any]]):
    async def _inner(**kwargs) -> None:
        target.append(kwargs)

    return _inner
