from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.db.models.processed_updates import ProcessedUpdate
from app.db.session import SessionLocal
from app.workers.tasks import telegram_updates

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
async def test_telegram_update_duplicate_delivery_processed_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
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
