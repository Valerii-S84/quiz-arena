from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from app.game.tournaments.constants import TOURNAMENT_STATUS_REGISTRATION
from app.workers.tasks import daily_cup_prestart_reminder


class _DummyBotSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _RecordingBot:
    def __init__(
        self,
        *,
        forbidden_chat_id: int | None = None,
        failing_chat_id: int | None = None,
    ) -> None:
        self.session = _DummyBotSession()
        self.forbidden_chat_id = forbidden_chat_id
        self.failing_chat_id = failing_chat_id
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, **kwargs) -> None:
        chat_id = int(kwargs["chat_id"])
        if self.forbidden_chat_id is not None and chat_id == self.forbidden_chat_id:
            raise TelegramForbiddenError(
                method=SendMessage(chat_id=chat_id, text="x"),
                message="forbidden",
            )
        if self.failing_chat_id is not None and chat_id == self.failing_chat_id:
            raise RuntimeError("boom")
        self.messages.append(kwargs)


class _AsyncBeginContext:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        return None


def _session_local_with_sessions(*sessions: object) -> SimpleNamespace:
    remaining = list(sessions)

    def _begin() -> _AsyncBeginContext:
        return _AsyncBeginContext(remaining.pop(0))

    return SimpleNamespace(begin=_begin)


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


@pytest.mark.asyncio
async def test_prestart_reminder_returns_zeroes_when_tournament_not_in_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = SimpleNamespace(
        id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        status="ROUND_1",
    )

    async def _unexpected_targets(*args, **kwargs):
        del args, kwargs
        pytest.fail("targets should not be loaded outside registration state")

    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "SessionLocal",
        _session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "ensure_daily_cup_registration_tournament",
        _async_return(tournament),
    )
    monkeypatch.setattr(
        daily_cup_prestart_reminder.UsersRepo,
        "list_daily_cup_registered_reminder_targets",
        _unexpected_targets,
    )

    result = await daily_cup_prestart_reminder.send_daily_cup_prestart_reminder_async()

    assert result == {
        "processed": 0,
        "users_scanned_total": 0,
        "sent_total": 0,
        "skipped_total": 0,
    }


@pytest.mark.asyncio
async def test_prestart_reminder_sends_in_batches_and_logs_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = SimpleNamespace(
        id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        status=TOURNAMENT_STATUS_REGISTRATION,
    )
    bot = _RecordingBot()
    info_logs: list[dict[str, object]] = []
    target_calls: list[dict[str, object]] = []
    keyboard = object()
    batches = [
        [(10, 10010), (20, 10020)],
        [(30, 10030)],
        [],
    ]

    async def _fake_targets(session, *, tournament_id, after_user_id, limit):
        del session
        target_calls.append(
            {
                "tournament_id": tournament_id,
                "after_user_id": after_user_id,
                "limit": limit,
            }
        )
        return batches.pop(0)

    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "SessionLocal",
        _session_local_with_sessions(SimpleNamespace(), SimpleNamespace(), SimpleNamespace(), SimpleNamespace()),
    )
    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "ensure_daily_cup_registration_tournament",
        _async_return(tournament),
    )
    monkeypatch.setattr(
        daily_cup_prestart_reminder.UsersRepo,
        "list_daily_cup_registered_reminder_targets",
        _fake_targets,
    )
    monkeypatch.setattr(daily_cup_prestart_reminder, "build_bot", lambda: bot)
    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "build_daily_cup_lobby_keyboard",
        lambda **kwargs: keyboard,
    )
    monkeypatch.setattr(
        daily_cup_prestart_reminder.logger,
        "info",
        lambda event, **kwargs: info_logs.append({"event": event, **kwargs}),
    )
    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "now_utc",
        lambda: "fixed-now",
    )

    result = await daily_cup_prestart_reminder.send_daily_cup_prestart_reminder_async()

    assert result == {
        "processed": 1,
        "users_scanned_total": 3,
        "sent_total": 3,
        "skipped_total": 0,
    }
    assert [call["after_user_id"] for call in target_calls] == [None, 20, 30]
    assert all(call["limit"] == daily_cup_prestart_reminder.DAILY_CUP_PUSH_BATCH_SIZE for call in target_calls)
    assert [int(message["chat_id"]) for message in bot.messages] == [10010, 10020, 10030]
    assert all(message["reply_markup"] is keyboard for message in bot.messages)
    assert bot.session.closed is True
    assert info_logs == [{"event": "daily_cup_prestart_reminder_processed", **result}]


@pytest.mark.asyncio
async def test_prestart_reminder_counts_forbidden_and_unexpected_errors_as_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = SimpleNamespace(
        id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        status=TOURNAMENT_STATUS_REGISTRATION,
    )
    bot = _RecordingBot(forbidden_chat_id=10020, failing_chat_id=10030)
    responses = [[(10, 10010), (20, 10020), (30, 10030)], []]

    async def _fake_targets(session, *, tournament_id, after_user_id, limit):
        del session, tournament_id, after_user_id, limit
        return responses.pop(0)

    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "SessionLocal",
        _session_local_with_sessions(SimpleNamespace(), SimpleNamespace(), SimpleNamespace()),
    )
    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "ensure_daily_cup_registration_tournament",
        _async_return(tournament),
    )
    monkeypatch.setattr(
        daily_cup_prestart_reminder.UsersRepo,
        "list_daily_cup_registered_reminder_targets",
        _fake_targets,
    )
    monkeypatch.setattr(daily_cup_prestart_reminder, "build_bot", lambda: bot)
    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "build_daily_cup_lobby_keyboard",
        lambda **kwargs: "keyboard",
    )

    result = await daily_cup_prestart_reminder.send_daily_cup_prestart_reminder_async()

    assert result == {
        "processed": 1,
        "users_scanned_total": 3,
        "sent_total": 1,
        "skipped_total": 2,
    }
    assert [int(message["chat_id"]) for message in bot.messages] == [10010]
    assert bot.session.closed is True


@pytest.mark.asyncio
async def test_prestart_reminder_closes_bot_when_no_targets_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = SimpleNamespace(
        id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        status=TOURNAMENT_STATUS_REGISTRATION,
    )
    bot = _RecordingBot()

    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "SessionLocal",
        _session_local_with_sessions(SimpleNamespace(), SimpleNamespace()),
    )
    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "ensure_daily_cup_registration_tournament",
        _async_return(tournament),
    )
    monkeypatch.setattr(
        daily_cup_prestart_reminder.UsersRepo,
        "list_daily_cup_registered_reminder_targets",
        _async_return([]),
    )
    monkeypatch.setattr(daily_cup_prestart_reminder, "build_bot", lambda: bot)
    monkeypatch.setattr(
        daily_cup_prestart_reminder,
        "build_daily_cup_lobby_keyboard",
        lambda **kwargs: "keyboard",
    )

    result = await daily_cup_prestart_reminder.send_daily_cup_prestart_reminder_async()

    assert result == {
        "processed": 1,
        "users_scanned_total": 0,
        "sent_total": 0,
        "skipped_total": 0,
    }
    assert bot.messages == []
    assert bot.session.closed is True
