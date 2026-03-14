from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import SendMessage
from sqlalchemy import select

from app.db.models.outbox_events import OutboxEvent
from app.db.models.processed_updates import ProcessedUpdate
from app.db.session import SessionLocal
from app.workers.tasks import telegram_updates
from app.workers.tasks.telegram_updates_config import (
    EVENT_TELEGRAM_UPDATE_RECLAIMED,
    EVENT_TELEGRAM_UPDATE_RETRY_SCHEDULED,
)

UTC = timezone.utc


class _DummyBotSession:
    async def close(self) -> None:
        return None


class _DummyBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.feed_calls = 0

    async def feed_update(self, _bot: _DummyBot, _update: object) -> None:
        self.feed_calls += 1
        await asyncio.sleep(0)


class _RaisingDispatcher:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.feed_calls = 0

    async def feed_update(self, _bot: _DummyBot, _update: object) -> None:
        self.feed_calls += 1
        raise self._exc


def _minimal_message_update_payload(*, update_id: int, telegram_user_id: int) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 101,
            "date": int(datetime.now(UTC).timestamp()),
            "chat": {
                "id": telegram_user_id,
                "type": "private",
                "first_name": "Load",
            },
            "from": {
                "id": telegram_user_id,
                "is_bot": False,
                "first_name": "Load",
                "language_code": "de",
            },
            "text": "/start",
            "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
        },
    }


@pytest.mark.asyncio
async def test_telegram_update_duplicate_delivery_processed_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = _RecordingDispatcher()
    monkeypatch.setattr(telegram_updates, "build_bot", lambda: _DummyBot())
    monkeypatch.setattr(telegram_updates, "build_dispatcher", lambda: dispatcher)

    update_id = 987_654_321
    update_payload = _minimal_message_update_payload(
        update_id=update_id,
        telegram_user_id=90_123_456_789,
    )

    first_result, second_result = await asyncio.gather(
        telegram_updates.process_update_async(update_payload, update_id=update_id),
        telegram_updates.process_update_async(update_payload, update_id=update_id),
    )

    assert sorted([first_result, second_result]) == ["duplicate", "processed"]
    assert dispatcher.feed_calls == 1

    async with SessionLocal.begin() as session:
        row = await session.get(ProcessedUpdate, update_id)
    assert row is not None
    assert row.status == "PROCESSED"


@pytest.mark.asyncio
async def test_telegram_update_reclaims_failed_slot_and_reprocesses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = _RecordingDispatcher()
    monkeypatch.setattr(telegram_updates, "build_bot", lambda: _DummyBot())
    monkeypatch.setattr(telegram_updates, "build_dispatcher", lambda: dispatcher)

    update_id = 987_654_322
    update_payload = _minimal_message_update_payload(
        update_id=update_id,
        telegram_user_id=90_123_456_790,
    )

    async with SessionLocal.begin() as session:
        session.add(
            ProcessedUpdate(
                update_id=update_id,
                processed_at=datetime.now(UTC) - timedelta(minutes=5),
                status="FAILED",
                processing_task_id="failed-task",
            )
        )

    result = await telegram_updates.process_update_async(
        update_payload,
        update_id=update_id,
        task_id="retry-task",
    )

    assert result == "processed"
    assert dispatcher.feed_calls == 1

    async with SessionLocal.begin() as session:
        row = await session.get(ProcessedUpdate, update_id)
    assert row is not None
    assert row.status == "PROCESSED"
    assert row.processing_task_id is None


@pytest.mark.asyncio
async def test_telegram_update_reclaims_stale_processing_slot_and_writes_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = _RecordingDispatcher()
    monkeypatch.setattr(telegram_updates, "build_bot", lambda: _DummyBot())
    monkeypatch.setattr(telegram_updates, "build_dispatcher", lambda: dispatcher)

    update_id = 987_654_323
    update_payload = _minimal_message_update_payload(
        update_id=update_id,
        telegram_user_id=90_123_456_791,
    )

    async with SessionLocal.begin() as session:
        session.add(
            ProcessedUpdate(
                update_id=update_id,
                processed_at=datetime.now(UTC)
                - timedelta(seconds=telegram_updates.PROCESSING_TTL_SECONDS + 5),
                status="PROCESSING",
                processing_task_id="stale-task",
            )
        )

    result = await telegram_updates.process_update_async(
        update_payload,
        update_id=update_id,
        task_id="reclaimed-task",
    )

    assert result == "processed"
    assert dispatcher.feed_calls == 1

    async with SessionLocal.begin() as session:
        row = await session.get(ProcessedUpdate, update_id)
        event = await session.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == EVENT_TELEGRAM_UPDATE_RECLAIMED)
        )
    assert row is not None
    assert row.status == "PROCESSED"
    assert event is not None
    assert event.status == "SENT"
    assert event.payload["update_id"] == update_id
    assert event.payload["task_id"] == "reclaimed-task"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc_factory", "update_id"),
    [
        (
            lambda: TelegramBadRequest(
                method=SendMessage(chat_id=1, text="x"),
                message="bad request",
            ),
            987_654_324,
        ),
        (
            lambda: TelegramForbiddenError(
                method=SendMessage(chat_id=1, text="x"),
                message="forbidden",
            ),
            987_654_325,
        ),
    ],
)
async def test_telegram_update_non_retryable_errors_mark_processed(
    monkeypatch: pytest.MonkeyPatch,
    exc_factory,
    update_id: int,
) -> None:
    dispatcher = _RaisingDispatcher(exc_factory())
    monkeypatch.setattr(telegram_updates, "build_bot", lambda: _DummyBot())
    monkeypatch.setattr(telegram_updates, "build_dispatcher", lambda: dispatcher)

    update_payload = _minimal_message_update_payload(
        update_id=update_id,
        telegram_user_id=90_123_456_792,
    )

    result = await telegram_updates.process_update_async(update_payload, update_id=update_id)

    assert result == "processed"
    assert dispatcher.feed_calls == 1

    async with SessionLocal.begin() as session:
        row = await session.get(ProcessedUpdate, update_id)
    assert row is not None
    assert row.status == "PROCESSED"
    assert row.processing_task_id is None


@pytest.mark.asyncio
async def test_telegram_update_unexpected_error_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update_id = 987_654_326
    update_payload = _minimal_message_update_payload(
        update_id=update_id,
        telegram_user_id=90_123_456_793,
    )
    dispatcher = _RaisingDispatcher(RuntimeError("boom"))

    monkeypatch.setattr(telegram_updates, "build_bot", lambda: _DummyBot())
    monkeypatch.setattr(telegram_updates, "build_dispatcher", lambda: dispatcher)

    with pytest.raises(RuntimeError, match="boom"):
        await telegram_updates.process_update_async(update_payload, update_id=update_id)

    async with SessionLocal.begin() as session:
        row = await session.get(ProcessedUpdate, update_id)
    assert row is not None
    assert row.status == "FAILED"
    assert row.processing_task_id is None


def test_telegram_update_task_unexpected_error_writes_retry_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update_id = 987_654_327
    task = telegram_updates.process_telegram_update._get_current_object()
    retry_calls: list[dict[str, object]] = []

    async def fake_process_update_async(
        update_payload: dict[str, object],
        *,
        update_id: int,
        task_id: str | None = None,
    ) -> str:
        del update_payload, update_id, task_id
        raise RuntimeError("boom")

    def fake_retry(*, exc: Exception, countdown: int, max_retries: int):
        retry_calls.append(
            {
                "error": str(exc),
                "countdown": countdown,
                "max_retries": max_retries,
            }
        )
        raise RuntimeError("retry-triggered")

    monkeypatch.setattr(telegram_updates, "process_update_async", fake_process_update_async)
    monkeypatch.setattr(telegram_updates, "_retry_backoff_seconds", lambda **kwargs: 7)
    monkeypatch.setattr(task, "retry", fake_retry)

    with pytest.raises(RuntimeError, match="retry-triggered"):
        task(update_payload={"update_id": update_id})

    assert retry_calls == [{"error": "boom", "countdown": 7, "max_retries": task.max_retries}]

    async def _load_event() -> OutboxEvent | None:
        async with SessionLocal.begin() as session:
            return await session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == EVENT_TELEGRAM_UPDATE_RETRY_SCHEDULED
                )
            )

    event = asyncio.run(_load_event())
    assert event is not None
    assert event.status == "SENT"
    assert event.payload["update_id"] == update_id
    assert event.payload["retry_in_seconds"] == 7
