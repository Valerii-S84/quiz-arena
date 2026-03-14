from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from app.workers.tasks import daily_cup_turn_reminder


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


def test_resolve_turn_reminder_users_for_creator_done() -> None:
    challenge = SimpleNamespace(
        status="CREATOR_DONE",
        creator_user_id=10,
        opponent_user_id=22,
    )

    resolved = daily_cup_turn_reminder.resolve_turn_reminder_users(challenge=challenge)
    assert resolved == ((22, 10),)


def test_resolve_turn_reminder_users_for_opponent_done() -> None:
    challenge = SimpleNamespace(
        status="OPPONENT_DONE",
        creator_user_id=10,
        opponent_user_id=22,
    )

    resolved = daily_cup_turn_reminder.resolve_turn_reminder_users(challenge=challenge)
    assert resolved == ((10, 22),)


def test_resolve_turn_reminder_users_for_accepted_returns_both_users() -> None:
    challenge = SimpleNamespace(
        status="ACCEPTED",
        creator_user_id=10,
        opponent_user_id=22,
    )

    resolved = daily_cup_turn_reminder.resolve_turn_reminder_users(challenge=challenge)
    assert resolved == ((10, 22), (22, 10))


def test_resolve_turn_reminder_users_returns_empty_for_other_status() -> None:
    challenge = SimpleNamespace(
        status="PENDING",
        creator_user_id=10,
        opponent_user_id=22,
    )

    resolved = daily_cup_turn_reminder.resolve_turn_reminder_users(challenge=challenge)
    assert resolved == ()


def test_resolve_turn_reminder_opponent_label_uses_arena_bot_for_self_match() -> None:
    label = daily_cup_turn_reminder._resolve_turn_reminder_opponent_label(
        target_user_id=10,
        opponent_user_id=10,
        user_labels={10: "Ich"},
    )
    assert label == "Arena Bot"


@pytest.mark.asyncio
async def test_turn_reminders_return_zeroes_when_no_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info_logs: list[dict[str, object]] = []

    async def _no_candidates(*args, **kwargs):
        del args, kwargs
        return []

    monkeypatch.setattr(
        daily_cup_turn_reminder,
        "now_utc",
        lambda: datetime(2026, 3, 13, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder,
        "SessionLocal",
        _session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder.TournamentMatchesRepo,
        "list_daily_cup_turn_reminder_candidates_for_update",
        _no_candidates,
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder.logger,
        "info",
        lambda event, **kwargs: info_logs.append({"event": event, **kwargs}),
    )

    result = await daily_cup_turn_reminder.run_daily_cup_turn_reminders_async(batch_size=0)

    assert result == {
        "processed": 1,
        "batch_size": 1,
        "scanned_total": 0,
        "queued_total": 0,
        "sent_total": 0,
        "skipped_total": 0,
        "failed_total": 0,
    }
    assert info_logs == [{"event": "daily_cup_turn_reminders_processed", **result}]


@pytest.mark.asyncio
async def test_turn_reminders_mark_candidates_deduplicate_targets_and_store_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_value = datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)
    tournament_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    bot = _RecordingBot()
    info_logs: list[dict[str, object]] = []
    store_calls: list[dict[str, object]] = []
    list_by_ids_calls: list[set[int]] = []

    challenge_primary = SimpleNamespace(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        creator_user_id=10,
        opponent_user_id=20,
        status="ACCEPTED",
        expires_last_chance_notified_at=None,
        updated_at=None,
    )
    challenge_duplicate = SimpleNamespace(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        creator_user_id=10,
        opponent_user_id=20,
        status="OPPONENT_DONE",
        expires_last_chance_notified_at=None,
        updated_at=None,
    )
    challenge_missing_chat = SimpleNamespace(
        id=UUID("33333333-3333-3333-3333-333333333333"),
        creator_user_id=10,
        opponent_user_id=30,
        status="CREATOR_DONE",
        expires_last_chance_notified_at=None,
        updated_at=None,
    )
    candidates = [
        (
            SimpleNamespace(
                tournament_id=tournament_id,
                deadline=datetime(2026, 3, 13, 12, 30, tzinfo=timezone.utc),
            ),
            challenge_primary,
        ),
        (
            SimpleNamespace(
                tournament_id=tournament_id,
                deadline=datetime(2026, 3, 13, 12, 31, tzinfo=timezone.utc),
            ),
            challenge_duplicate,
        ),
        (
            SimpleNamespace(
                tournament_id=tournament_id,
                deadline=datetime(2026, 3, 13, 12, 32, tzinfo=timezone.utc),
            ),
            challenge_missing_chat,
        ),
    ]

    async def _fake_candidates(*args, **kwargs):
        del args, kwargs
        return candidates

    async def _fake_list_by_ids(session, user_ids: list[int]):
        del session
        list_by_ids_calls.append(set(user_ids))
        return [
            SimpleNamespace(id=10, telegram_user_id=10010, username="anna", first_name="Anna"),
            SimpleNamespace(id=20, telegram_user_id=10020, username="bert", first_name="Bert"),
        ]

    async def _fake_store_push_sent_events(**kwargs):
        store_calls.append(kwargs)

    monkeypatch.setattr(daily_cup_turn_reminder, "now_utc", lambda: now_value)
    monkeypatch.setattr(
        daily_cup_turn_reminder,
        "SessionLocal",
        _session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder.TournamentMatchesRepo,
        "list_daily_cup_turn_reminder_candidates_for_update",
        _fake_candidates,
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder.UsersRepo,
        "list_by_ids",
        _fake_list_by_ids,
    )
    monkeypatch.setattr(daily_cup_turn_reminder, "build_bot", lambda: bot)
    monkeypatch.setattr(
        daily_cup_turn_reminder,
        "build_daily_cup_lobby_keyboard",
        lambda **kwargs: {"challenge_id": kwargs["play_challenge_id"]},
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder,
        "format_deadline",
        lambda deadline: f"deadline:{deadline.isoformat()}",
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder,
        "store_push_sent_events",
        _fake_store_push_sent_events,
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder.logger,
        "info",
        lambda event, **kwargs: info_logs.append({"event": event, **kwargs}),
    )

    result = await daily_cup_turn_reminder.run_daily_cup_turn_reminders_async(batch_size=5)

    assert result == {
        "processed": 1,
        "batch_size": 5,
        "scanned_total": 3,
        "queued_total": 2,
        "sent_total": 2,
        "skipped_total": 2,
        "failed_total": 0,
    }
    assert list_by_ids_calls == [{10, 20, 30}]
    assert [int(message["chat_id"]) for message in bot.messages] == [10010, 10020]
    assert bot.session.closed is True
    assert challenge_primary.expires_last_chance_notified_at == now_value
    assert challenge_primary.updated_at == now_value
    assert challenge_duplicate.expires_last_chance_notified_at == now_value
    assert challenge_missing_chat.expires_last_chance_notified_at == now_value
    assert store_calls == [
        {
            "event_type": "daily_cup_turn_reminder_sent",
            "tournament_id": tournament_id,
            "user_ids": [10, 20],
            "happened_at": now_value,
        }
    ]
    assert info_logs == [{"event": "daily_cup_turn_reminders_processed", **result}]


@pytest.mark.asyncio
async def test_turn_reminders_count_send_failures_and_swallow_event_store_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_value = datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)
    tournament_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    bot = _RecordingBot(forbidden_chat_id=10020, failing_chat_id=10030)
    warning_logs: list[dict[str, object]] = []

    challenge = SimpleNamespace(
        id=UUID("44444444-4444-4444-4444-444444444444"),
        creator_user_id=10,
        opponent_user_id=20,
        status="ACCEPTED",
        expires_last_chance_notified_at=None,
        updated_at=None,
    )
    second_challenge = SimpleNamespace(
        id=UUID("55555555-5555-5555-5555-555555555555"),
        creator_user_id=40,
        opponent_user_id=30,
        status="CREATOR_DONE",
        expires_last_chance_notified_at=None,
        updated_at=None,
    )

    async def _fake_candidates(*args, **kwargs):
        del args, kwargs
        return [
            (
                SimpleNamespace(
                    tournament_id=tournament_id,
                    deadline=datetime(2026, 3, 13, 12, 30, tzinfo=timezone.utc),
                ),
                challenge,
            ),
            (
                SimpleNamespace(
                    tournament_id=tournament_id,
                    deadline=datetime(2026, 3, 13, 12, 31, tzinfo=timezone.utc),
                ),
                second_challenge,
            ),
        ]

    async def _fake_list_by_ids(session, user_ids: list[int]):
        del session, user_ids
        return [
            SimpleNamespace(id=10, telegram_user_id=10010, username="anna", first_name="Anna"),
            SimpleNamespace(id=20, telegram_user_id=10020, username="bert", first_name="Bert"),
            SimpleNamespace(id=30, telegram_user_id=10030, username="cora", first_name="Cora"),
            SimpleNamespace(id=40, telegram_user_id=10040, username="dora", first_name="Dora"),
        ]

    async def _failing_store_push_sent_events(**kwargs):
        del kwargs
        raise RuntimeError("store failed")

    monkeypatch.setattr(daily_cup_turn_reminder, "now_utc", lambda: now_value)
    monkeypatch.setattr(
        daily_cup_turn_reminder,
        "SessionLocal",
        _session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder.TournamentMatchesRepo,
        "list_daily_cup_turn_reminder_candidates_for_update",
        _fake_candidates,
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder.UsersRepo,
        "list_by_ids",
        _fake_list_by_ids,
    )
    monkeypatch.setattr(daily_cup_turn_reminder, "build_bot", lambda: bot)
    monkeypatch.setattr(
        daily_cup_turn_reminder,
        "build_daily_cup_lobby_keyboard",
        lambda **kwargs: {"challenge_id": kwargs["play_challenge_id"]},
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder,
        "format_deadline",
        lambda deadline: f"deadline:{deadline.isoformat()}",
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder,
        "store_push_sent_events",
        _failing_store_push_sent_events,
    )
    monkeypatch.setattr(
        daily_cup_turn_reminder.logger,
        "warning",
        lambda event, **kwargs: warning_logs.append({"event": event, **kwargs}),
    )

    result = await daily_cup_turn_reminder.run_daily_cup_turn_reminders_async(batch_size=10)

    assert result == {
        "processed": 1,
        "batch_size": 10,
        "scanned_total": 2,
        "queued_total": 3,
        "sent_total": 1,
        "skipped_total": 0,
        "failed_total": 2,
    }
    assert [int(message["chat_id"]) for message in bot.messages] == [10010]
    assert bot.session.closed is True
    assert [log["event"] for log in warning_logs] == [
        "daily_cup_turn_reminder_send_failed",
        "daily_cup_turn_reminder_event_store_failed",
    ]
