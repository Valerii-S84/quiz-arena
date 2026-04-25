from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest

from app.bot.texts.de import TEXTS_DE
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.workers.tasks import daily_cup_prestart_reminder
from app.workers.tasks.daily_cup_time import get_daily_cup_window
from tests.integration.friend_challenge_fixtures import _create_user
from tests.integration.test_daily_cup_worker_integration import _DummyBotSession
from tests.integration.test_private_tournament_service_integration import _ensure_tournament_schema

UTC = timezone.utc


class _RecordingBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)


class _SlowRecordingBot:
    def __init__(self, *, sink: list[dict[str, Any]], delay_seconds: float) -> None:
        self.session = _DummyBotSession()
        self._sink = sink
        self._delay_seconds = delay_seconds

    async def send_message(self, **kwargs: Any) -> None:
        await asyncio.sleep(self._delay_seconds)
        self._sink.append(kwargs)


async def _set_last_seen(*, user_id: int, seen_at: datetime) -> None:
    async with SessionLocal.begin() as session:
        await UsersRepo.touch_last_seen(session, user_id=user_id, seen_at=seen_at)


async def _get_today_registration_tournament_id(*, now_utc: datetime) -> UUID:
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_type_and_registration_deadline(
            session,
            tournament_type="DAILY_ARENA",
            registration_deadline=get_daily_cup_window(now_utc=now_utc).close_at_utc,
        )
        assert tournament is not None
        return tournament.id


@pytest.mark.asyncio
async def test_daily_cup_prestart_reminder_integration_sends_final_registration_push(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 3, 1, 15, 50, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_id = await _create_user("daily_cup_prestart_int")
    await _set_last_seen(user_id=user_id, seen_at=now_utc - timedelta(days=1))

    bot = _RecordingBot()
    monkeypatch.setattr(daily_cup_prestart_reminder, "now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_prestart_reminder, "build_bot", lambda: bot)

    result = await daily_cup_prestart_reminder.send_daily_cup_prestart_reminder_async()

    assert result == {
        "processed": 1,
        "users_scanned_total": 1,
        "sent_total": 1,
        "skipped_total": 0,
    }
    assert [message["text"] for message in bot.messages] == [
        TEXTS_DE["msg.daily_cup.prestart_reminder"]
    ]

    tournament_id = await _get_today_registration_tournament_id(now_utc=now_utc)
    join_button = bot.messages[0]["reply_markup"].inline_keyboard[0][0]
    assert join_button.text == "✅ Ich bin dabei!"
    assert join_button.callback_data == f"daily:cup:join:{tournament_id}"


@pytest.mark.asyncio
async def test_daily_cup_prestart_reminder_repeat_run_does_not_send_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 3, 1, 15, 50, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_id = await _create_user("daily_cup_prestart_repeat")
    await _set_last_seen(user_id=user_id, seen_at=now_utc - timedelta(days=1))

    bot = _RecordingBot()
    monkeypatch.setattr(daily_cup_prestart_reminder, "now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_prestart_reminder, "build_bot", lambda: bot)

    first = await daily_cup_prestart_reminder.send_daily_cup_prestart_reminder_async()
    second = await daily_cup_prestart_reminder.send_daily_cup_prestart_reminder_async()

    assert first["sent_total"] == 1
    assert second["sent_total"] == 0
    assert second["skipped_total"] == 1
    assert len(bot.messages) == 1


@pytest.mark.asyncio
async def test_daily_cup_prestart_reminder_parallel_workers_send_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 3, 1, 15, 50, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_id = await _create_user("daily_cup_prestart_parallel")
    await _set_last_seen(user_id=user_id, seen_at=now_utc - timedelta(days=1))

    messages: list[dict[str, Any]] = []
    monkeypatch.setattr(daily_cup_prestart_reminder, "now_utc", lambda: now_utc)
    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "build_bot",
        lambda: _SlowRecordingBot(sink=messages, delay_seconds=0.2),
    )

    first, second = await asyncio.gather(
        daily_cup_prestart_reminder.send_daily_cup_prestart_reminder_async(),
        daily_cup_prestart_reminder.send_daily_cup_prestart_reminder_async(),
    )

    assert first["sent_total"] + second["sent_total"] == 1
    assert len(messages) == 1
