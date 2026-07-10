from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup

from app.game.arena_duels.constants import (
    ARENA_BEATEN_NOTIFICATION_EVENT,
    ARENA_BEATEN_NOTIFICATION_TYPE,
)
from app.game.arena_duels.types import ArenaBeatenNotification
from app.workers.tasks import arena_duels
from app.workers.tasks import arena_duels_notification_delivery as delivery
from app.workers.tasks.arena_duels_notification_content import (
    build_arena_beaten_notification_keyboard,
    build_notification_text,
    classify_beaten_notification_action_mode,
)
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


class _SessionLocal:
    def __init__(self, session: object) -> None:
        self._session = session

    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(self._session)


class _DummyBot:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, object]] = []

    async def send_message(self, **kwargs) -> None:
        self.sent_messages.append(kwargs)


class _FlakyBot:
    def __init__(self) -> None:
        self.attempted_messages: list[dict[str, object]] = []
        self.sent_messages: list[dict[str, object]] = []
        self.fail_next_send = True

    async def send_message(self, **kwargs) -> None:
        self.attempted_messages.append(kwargs)
        if self.fail_next_send:
            self.fail_next_send = False
            raise RuntimeError("telegram send failed")
        self.sent_messages.append(kwargs)


def _notification(
    *,
    previous_score: int = 6,
    previous_time_ms: int = 48_000,
    new_score: int = 7,
    new_time_ms: int = 52_000,
) -> ArenaBeatenNotification:
    return ArenaBeatenNotification(
        arena_duel_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        previous_best_attempt_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        previous_best_user_id=11,
        previous_best_score=previous_score,
        previous_best_time_ms=previous_time_ms,
        new_best_attempt_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        new_best_user_id=22,
        new_best_score=new_score,
        new_best_time_ms=new_time_ms,
        notification_type=ARENA_BEATEN_NOTIFICATION_TYPE,
    )


def _callbacks(reply_markup: InlineKeyboardMarkup) -> list[str]:
    return [
        button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


def test_send_arena_beaten_notification_records_key_after_successful_send(
    monkeypatch,
) -> None:
    recorded: list[dict[str, object]] = []
    bot = _DummyBot()
    delivery_calls = _patch_delivery_tracking(monkeypatch)

    async def _fake_lock_key(session, **kwargs) -> None:
        del session, kwargs

    async def _fake_has_event(session, **kwargs) -> bool:
        del session, kwargs
        return False

    async def _fake_create_once(session, **kwargs) -> bool:
        del session
        assert bot.sent_messages
        recorded.append(kwargs)
        return True

    async def _fake_list_by_ids(session, user_ids):
        del session
        assert list(user_ids) == [11, 22]
        return [
            SimpleNamespace(id=11, telegram_user_id=110_000_011),
            SimpleNamespace(id=22, telegram_user_id=220_000_022, username="anna"),
        ]

    monkeypatch.setattr(arena_duels, "SessionLocal", _SessionLocal(object()))
    monkeypatch.setattr(
        arena_duels.AnalyticsRepo,
        "lock_arena_beaten_notification_event_key",
        _fake_lock_key,
    )
    monkeypatch.setattr(
        arena_duels.AnalyticsRepo,
        "has_arena_beaten_notification_event",
        _fake_has_event,
    )
    monkeypatch.setattr(
        arena_duels.AnalyticsRepo,
        "create_arena_beaten_notification_event_once",
        _fake_create_once,
    )
    monkeypatch.setattr(arena_duels.UsersRepo, "list_by_ids", _fake_list_by_ids)

    result = asyncio.run(
        arena_duels.send_arena_beaten_notification(
            notification=_notification(),
            happened_at=NOW_UTC,
            bot=bot,
        )
    )

    assert result == {"sent_total": 1, "failed_total": 0, "skipped_total": 0}
    assert delivery_calls["sent"]
    payload = cast(dict[str, object], recorded[0]["payload"])
    assert recorded[0]["event_type"] == ARENA_BEATEN_NOTIFICATION_EVENT
    assert recorded[0]["user_id"] == 11
    assert payload["previous_best_attempt_id"] == str(_notification().previous_best_attempt_id)
    assert payload["new_best_attempt_id"] == str(_notification().new_best_attempt_id)
    assert payload["notification_type"] == ARENA_BEATEN_NOTIFICATION_TYPE
    assert bot.sent_messages[0]["chat_id"] == 110_000_011
    assert "@anna hat dich überholt" in str(bot.sent_messages[0]["text"])
    assert "+1 Antwort Unterschied." in str(bot.sent_messages[0]["text"])
    assert "Hol dir deinen Platz zurück?" in str(bot.sent_messages[0]["text"])
    assert "Du:\n6/7 · 00:48" in str(bot.sent_messages[0]["text"])
    assert "@anna:\n7/7 · 00:52" in str(bot.sent_messages[0]["text"])
    keyboard = cast(InlineKeyboardMarkup, bot.sent_messages[0]["reply_markup"])
    assert _callbacks(keyboard) == [
        "arena:revanche:cccccccc-cccc-cccc-cccc-cccccccccccc",
        "buy:FRIEND_CHALLENGE_5:duel:beaten_result",
        "buy:PREMIUM_WEEK:duel:beaten_result",
        "arena:list",
    ]


def test_beaten_notification_same_score_time_loss_uses_premium_revanche_moment() -> None:
    notification = _notification(
        previous_score=6,
        previous_time_ms=48_000,
        new_score=6,
        new_time_ms=41_000,
    )

    text = build_notification_text(notification=notification, challenger_label="@anna")
    keyboard = build_arena_beaten_notification_keyboard(
        source_attempt_id=str(notification.new_best_attempt_id),
        action_mode=classify_beaten_notification_action_mode(notification),
    )

    assert "nur wegen der Zeit" in text
    assert "7 Sekunden schneller." in text
    assert "Revanche?" in text
    assert _callbacks(keyboard) == [
        "arena:revanche:cccccccc-cccc-cccc-cccc-cccccccccccc",
        "buy:FRIEND_CHALLENGE_5:duel:beaten_result",
        "buy:PREMIUM_WEEK:duel:beaten_result",
        "arena:list",
    ]


def test_beaten_notification_large_score_gap_hides_monetization_rows() -> None:
    notification = _notification(
        previous_score=4,
        previous_time_ms=48_000,
        new_score=6,
        new_time_ms=52_000,
    )

    text = build_notification_text(notification=notification, challenger_label="@anna")
    keyboard = build_arena_beaten_notification_keyboard(
        source_attempt_id=str(notification.new_best_attempt_id),
        action_mode=classify_beaten_notification_action_mode(notification),
    )

    assert "2 richtige Antworten Unterschied." in text
    assert "Starte eine Revanche" in text
    assert _callbacks(keyboard) == [
        "arena:revanche:cccccccc-cccc-cccc-cccc-cccccccccccc",
        "arena:list",
    ]


def test_beaten_notification_weak_result_only_links_back_to_arena() -> None:
    notification = _notification(
        previous_score=2,
        previous_time_ms=48_000,
        new_score=7,
        new_time_ms=52_000,
    )

    text = build_notification_text(notification=notification, challenger_label="@anna")
    keyboard = build_arena_beaten_notification_keyboard(
        source_attempt_id=str(notification.new_best_attempt_id),
        action_mode=classify_beaten_notification_action_mode(notification),
    )

    assert "Wähle ein neues Duell in der Arena." in text
    assert _callbacks(keyboard) == ["arena:list"]


def test_send_arena_beaten_notification_skips_existing_sent_event(monkeypatch) -> None:
    bot = _DummyBot()
    delivery_calls = _patch_delivery_tracking(monkeypatch)

    async def _fake_lock_key(session, **kwargs) -> None:
        del session, kwargs

    async def _fake_has_event(session, **kwargs) -> bool:
        del session, kwargs
        return True

    async def _unexpected_create_once(*_args, **_kwargs) -> bool:
        raise AssertionError("duplicate notifications must not record another sent event")

    async def _unexpected_list_by_ids(*_args, **_kwargs):
        raise AssertionError("duplicate notifications must not resolve users or send")

    monkeypatch.setattr(arena_duels, "SessionLocal", _SessionLocal(object()))
    monkeypatch.setattr(
        arena_duels.AnalyticsRepo,
        "lock_arena_beaten_notification_event_key",
        _fake_lock_key,
    )
    monkeypatch.setattr(
        arena_duels.AnalyticsRepo,
        "has_arena_beaten_notification_event",
        _fake_has_event,
    )
    monkeypatch.setattr(
        arena_duels.AnalyticsRepo,
        "create_arena_beaten_notification_event_once",
        _unexpected_create_once,
    )
    monkeypatch.setattr(arena_duels.UsersRepo, "list_by_ids", _unexpected_list_by_ids)

    result = asyncio.run(
        arena_duels.send_arena_beaten_notification(
            notification=_notification(),
            happened_at=NOW_UTC,
            bot=bot,
        )
    )

    assert result == {"sent_total": 0, "failed_total": 0, "skipped_total": 1}
    assert bot.sent_messages == []
    assert delivery_calls["skipped"]


def test_send_arena_beaten_notification_does_not_record_failed_send_and_retries(
    monkeypatch,
) -> None:
    recorded: list[dict[str, object]] = []
    bot = _FlakyBot()
    delivery_calls = _patch_delivery_tracking(monkeypatch)

    async def _fake_lock_key(session, **kwargs) -> None:
        del session, kwargs

    async def _fake_has_event(session, **kwargs) -> bool:
        del session, kwargs
        return bool(recorded)

    async def _fake_create_once(session, **kwargs) -> bool:
        del session
        assert bot.sent_messages
        recorded.append(kwargs)
        return True

    async def _fake_list_by_ids(session, user_ids):
        del session
        assert list(user_ids) == [11, 22]
        return [
            SimpleNamespace(id=11, telegram_user_id=110_000_011),
            SimpleNamespace(id=22, telegram_user_id=220_000_022, username="anna"),
        ]

    monkeypatch.setattr(arena_duels, "SessionLocal", _SessionLocal(object()))
    monkeypatch.setattr(
        arena_duels.AnalyticsRepo,
        "lock_arena_beaten_notification_event_key",
        _fake_lock_key,
    )
    monkeypatch.setattr(
        arena_duels.AnalyticsRepo,
        "has_arena_beaten_notification_event",
        _fake_has_event,
    )
    monkeypatch.setattr(
        arena_duels.AnalyticsRepo,
        "create_arena_beaten_notification_event_once",
        _fake_create_once,
    )
    monkeypatch.setattr(arena_duels.UsersRepo, "list_by_ids", _fake_list_by_ids)

    first_result = asyncio.run(
        arena_duels.send_arena_beaten_notification(
            notification=_notification(),
            happened_at=NOW_UTC,
            bot=bot,
        )
    )
    second_result = asyncio.run(
        arena_duels.send_arena_beaten_notification(
            notification=_notification(),
            happened_at=NOW_UTC,
            bot=bot,
        )
    )
    third_result = asyncio.run(
        arena_duels.send_arena_beaten_notification(
            notification=_notification(),
            happened_at=NOW_UTC,
            bot=bot,
        )
    )

    assert first_result == {"sent_total": 0, "failed_total": 1, "skipped_total": 0}
    assert second_result == {"sent_total": 1, "failed_total": 0, "skipped_total": 0}
    assert third_result == {"sent_total": 0, "failed_total": 0, "skipped_total": 1}
    assert len(bot.attempted_messages) == 2
    assert len(bot.sent_messages) == 1
    assert len(recorded) == 1
    assert len(delivery_calls["failed"]) == 1
    assert len(delivery_calls["sent"]) == 1
    assert len(delivery_calls["skipped"]) == 1


def _patch_delivery_tracking(monkeypatch):
    calls: dict[str, list[dict[str, object]]] = {
        "prepare": [],
        "sent": [],
        "failed": [],
        "skipped": [],
    }

    async def _prepare(**kwargs):
        calls["prepare"].append(kwargs)
        return SimpleNamespace(
            should_send=True,
            idempotency_key=kwargs["target"].idempotency_key,
        )

    async def _sent(**kwargs):
        calls["sent"].append(kwargs)

    async def _failed(**kwargs):
        calls["failed"].append(kwargs)

    async def _skipped(**kwargs):
        calls["skipped"].append(kwargs)

    monkeypatch.setattr(delivery, "prepare_telegram_delivery", _prepare)
    monkeypatch.setattr(delivery, "mark_telegram_delivery_sent", _sent)
    monkeypatch.setattr(delivery, "mark_telegram_delivery_failed", _failed)
    monkeypatch.setattr(delivery, "record_telegram_delivery_skipped", _skipped)
    return calls
