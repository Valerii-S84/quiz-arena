from __future__ import annotations

from datetime import datetime, timezone

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from app.workers.tasks import friend_challenges_notifications


class _DummyBotSession:
    async def close(self) -> None:
        return None


class _BlockedBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()

    async def send_message(self, **kwargs):
        del kwargs
        raise TelegramForbiddenError(
            method=SendMessage(chat_id=1, text="x"),
            message="forbidden",
        )


class _RecordingBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()
        self.messages: list[dict[str, object]] = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return None


@pytest.mark.asyncio
async def test_send_deadline_notifications_walkover_with_blocked_user_does_not_crash(
    monkeypatch,
) -> None:
    async def _fake_resolve_targets(user_ids):
        return {user_id: user_id for user_id in user_ids}

    monkeypatch.setattr(friend_challenges_notifications, "build_bot", lambda: _BlockedBot())
    monkeypatch.setattr(
        friend_challenges_notifications,
        "resolve_telegram_targets",
        _fake_resolve_targets,
    )

    result = await friend_challenges_notifications.send_deadline_notifications(
        now_utc=datetime.now(timezone.utc),
        reminder_items=[],
        expired_items=[
            {
                "challenge_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "creator_user_id": 10,
                "opponent_user_id": 20,
                "creator_score": 2,
                "opponent_score": 1,
                "status": "WALKOVER",
                "previous_status": "ACCEPTED",
            }
        ],
    )

    reminders_sent, reminders_failed, expired_sent, expired_failed, _, events = result
    assert reminders_sent == 0
    assert reminders_failed == 0
    assert expired_sent == 0
    assert expired_failed == 2
    assert events[0]["status"] == "WALKOVER"


@pytest.mark.asyncio
async def test_send_deadline_notifications_sends_reminder_event(
    monkeypatch,
) -> None:
    bot = _RecordingBot()

    async def _fake_resolve_targets(user_ids):
        assert user_ids == {10}
        return {10: 10010}

    monkeypatch.setattr(friend_challenges_notifications, "build_bot", lambda: bot)
    monkeypatch.setattr(
        friend_challenges_notifications,
        "resolve_telegram_targets",
        _fake_resolve_targets,
    )

    result = await friend_challenges_notifications.send_deadline_notifications(
        now_utc=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
        reminder_items=[
            {
                "challenge_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "target_user_id": 10,
                "expires_at": datetime(2026, 3, 20, 10, 20, tzinfo=timezone.utc),
            }
        ],
        expired_items=[],
    )

    reminders_sent, reminders_failed, expired_sent, expired_failed, reminder_events, events = result
    assert reminders_sent == 1
    assert reminders_failed == 0
    assert expired_sent == 0
    assert expired_failed == 0
    assert len(bot.messages) == 1
    assert bot.messages[0]["chat_id"] == 10010
    assert reminder_events[0]["target_user_id"] == 10
    assert reminder_events[0]["sent_to"] == 1
    assert events == []


@pytest.mark.asyncio
async def test_send_deadline_notifications_pending_expired_only_notifies_creator(
    monkeypatch,
) -> None:
    bot = _RecordingBot()

    async def _fake_resolve_targets(user_ids):
        assert user_ids == {10, 20}
        return {10: 10010, 20: 10020}

    monkeypatch.setattr(friend_challenges_notifications, "build_bot", lambda: bot)
    monkeypatch.setattr(
        friend_challenges_notifications,
        "resolve_telegram_targets",
        _fake_resolve_targets,
    )

    result = await friend_challenges_notifications.send_deadline_notifications(
        now_utc=datetime.now(timezone.utc),
        reminder_items=[],
        expired_items=[
            {
                "challenge_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "creator_user_id": 10,
                "opponent_user_id": 20,
                "creator_score": 0,
                "opponent_score": 0,
                "status": "EXPIRED",
                "previous_status": "PENDING",
            }
        ],
    )

    reminders_sent, reminders_failed, expired_sent, expired_failed, _, events = result
    assert reminders_sent == 0
    assert reminders_failed == 0
    assert expired_sent == 1
    assert expired_failed == 0
    assert len(bot.messages) == 1
    assert bot.messages[0]["chat_id"] == 10010
    assert events[0]["status"] == "EXPIRED"
    assert events[0]["previous_status"] == "PENDING"
