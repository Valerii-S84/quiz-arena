from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.bot.handlers import gameplay_callbacks
from app.bot.texts.de import TEXTS_DE
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.service import join_daily_cup_by_id
from app.workers.tasks import daily_cup_async
from app.workers.tasks.daily_cup_time import format_close_time_local, get_daily_cup_window
from tests.integration.friend_challenge_fixtures import _create_user
from tests.integration.test_daily_cup_worker_integration import _DummyBotSession
from tests.integration.test_private_tournament_service_integration import _ensure_tournament_schema

UTC = timezone.utc


class _RecordingBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()
        self.messages: list[dict[str, object]] = []

    async def send_message(self, **kwargs: object) -> None:
        self.messages.append(kwargs)


class _SlowRecordingBot:
    def __init__(self, *, sink: list[dict[str, object]], delay_seconds: float) -> None:
        self.session = _DummyBotSession()
        self._sink = sink
        self._delay_seconds = delay_seconds

    async def send_message(self, **kwargs: object) -> None:
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
async def test_invite_registration_push_sends_single_message_with_registration_button(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 3, 1, 15, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_id = await _create_user("daily_cup_push_single")
    await _set_last_seen(user_id=user_id, seen_at=now_utc - timedelta(days=1))

    bot = _RecordingBot()
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "build_bot", lambda: bot)

    result = await daily_cup_async.send_daily_cup_invite_registration_async()

    assert int(result["sent_total"]) == 1
    assert len(bot.messages) == 1
    message = bot.messages[0]
    tournament_id = await _get_today_registration_tournament_id(now_utc=now_utc)
    expected_text = TEXTS_DE["msg.daily_cup.push.registration"].format(
        close_time=format_close_time_local(
            close_at_utc=get_daily_cup_window(now_utc=now_utc).close_at_utc
        )
    )
    assert message["text"] == expected_text
    button = message["reply_markup"].inline_keyboard[0][0]
    assert button.text == "✅ Ich bin dabei!"
    assert button.callback_data == f"daily:cup:join:{tournament_id}"


@pytest.mark.asyncio
async def test_invite_registration_push_repeat_run_does_not_send_twice(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 15, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_id = await _create_user("daily_cup_push_repeat")
    await _set_last_seen(user_id=user_id, seen_at=now_utc - timedelta(days=1))

    bot = _RecordingBot()
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "build_bot", lambda: bot)

    first = await daily_cup_async.send_daily_cup_invite_registration_async()
    second = await daily_cup_async.send_daily_cup_invite_registration_async()

    assert int(first["sent_total"]) == 1
    assert int(second["sent_total"]) == 0
    assert int(second["skipped_total"]) == 1
    assert len(bot.messages) == 1


@pytest.mark.asyncio
async def test_invite_registration_push_parallel_workers_send_once(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 15, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_id = await _create_user("daily_cup_push_parallel")
    await _set_last_seen(user_id=user_id, seen_at=now_utc - timedelta(days=1))

    messages: list[dict[str, object]] = []
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(
        daily_cup_async,
        "build_bot",
        lambda: _SlowRecordingBot(sink=messages, delay_seconds=0.2),
    )

    first, second = await asyncio.gather(
        daily_cup_async.send_daily_cup_invite_registration_async(),
        daily_cup_async.send_daily_cup_invite_registration_async(),
    )

    assert int(first["sent_total"]) + int(second["sent_total"]) == 1
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_invite_registration_button_payload_registers_user(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 15, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_id = await _create_user("daily_cup_push_button")
    await _set_last_seen(user_id=user_id, seen_at=now_utc - timedelta(days=1))

    bot = _RecordingBot()
    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "build_bot", lambda: bot)

    await daily_cup_async.send_daily_cup_invite_registration_async()

    button = bot.messages[0]["reply_markup"].inline_keyboard[0][0]
    tournament_id = gameplay_callbacks.parse_uuid_callback(
        pattern=gameplay_callbacks.DAILY_CUP_JOIN_RE,
        callback_data=button.callback_data,
    )
    assert tournament_id is not None

    async with SessionLocal.begin() as session:
        join_result = await join_daily_cup_by_id(
            session,
            user_id=user_id,
            tournament_id=tournament_id,
            now_utc=now_utc,
        )
        assert join_result.joined_now is True

        participant = await TournamentParticipantsRepo.get_for_tournament_user(
            session,
            tournament_id=tournament_id,
            user_id=user_id,
        )
        assert participant is not None
