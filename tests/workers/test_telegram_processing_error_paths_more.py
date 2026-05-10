from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery

from app.workers.tasks import telegram_updates_processing as processing
from tests.workers.payments_reliability_async_support import SessionLocalStub


@pytest.mark.asyncio
async def test_process_update_marks_non_retryable_errors_processed(monkeypatch) -> None:
    statuses: list[dict[str, object]] = []
    bot = SimpleNamespace(session=SimpleNamespace(close=_async_return(None)))

    async def _bad_request(*_args, **_kwargs):
        raise TelegramBadRequest(method=AnswerCallbackQuery(callback_query_id="1"), message="bad")

    monkeypatch.setattr(processing, "_acquire_processing_slot", _async_return("created"))
    monkeypatch.setattr(processing, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(processing.Update, "model_validate", lambda payload: payload)
    monkeypatch.setattr(processing.ProcessedUpdatesRepo, "set_status", _append_kwargs(statuses))
    _patch_telegram_factories(monkeypatch, bot=bot, feed_update=_bad_request)

    assert await processing.process_update_async({"update_id": 1}, update_id=1) == "processed"
    assert statuses == [{"update_id": 1, "status": "PROCESSED", "processing_task_id": None}]


@pytest.mark.asyncio
async def test_process_update_marks_generic_errors_failed(monkeypatch) -> None:
    statuses: list[dict[str, object]] = []
    bot = SimpleNamespace(session=SimpleNamespace(close=_async_return(None)))

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(processing, "_acquire_processing_slot", _async_return("created"))
    monkeypatch.setattr(processing, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(processing.Update, "model_validate", lambda payload: payload)
    monkeypatch.setattr(processing.ProcessedUpdatesRepo, "set_status", _append_kwargs(statuses))
    _patch_telegram_factories(monkeypatch, bot=bot, feed_update=_boom)

    with pytest.raises(RuntimeError):
        await processing.process_update_async({"update_id": 1}, update_id=1)

    assert statuses == [{"update_id": 1, "status": "FAILED", "processing_task_id": None}]


def _patch_telegram_factories(monkeypatch, *, bot, feed_update) -> None:
    from app.workers.tasks import telegram_updates

    monkeypatch.setattr(telegram_updates, "build_bot", lambda: bot)
    monkeypatch.setattr(
        telegram_updates,
        "build_dispatcher",
        lambda: SimpleNamespace(feed_update=feed_update),
    )


def _append_kwargs(target: list[dict[str, object]]):
    async def _inner(_session, **kwargs) -> None:
        target.append(kwargs)

    return _inner


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
