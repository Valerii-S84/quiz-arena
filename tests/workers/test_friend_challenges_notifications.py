from __future__ import annotations

from datetime import datetime, timezone

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup

from app.bot.texts.de import TEXTS_DE
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


class _RecordingBotSession:
    async def close(self) -> None:
        return None


class _RecordingBot:
    def __init__(self) -> None:
        self.session = _RecordingBotSession()
        self.sent_messages: list[dict[str, object]] = []

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)


@pytest.mark.asyncio
async def test_send_deadline_notifications_pending_expired_uses_canonical_close_keyboard(
    monkeypatch,
) -> None:
    bot = _RecordingBot()

    async def _fake_resolve_targets(user_ids):
        return {user_id: user_id for user_id in user_ids}

    monkeypatch.setattr(friend_challenges_notifications, "build_bot", lambda: bot)
    monkeypatch.setattr(
        friend_challenges_notifications,
        "resolve_telegram_targets",
        _fake_resolve_targets,
    )

    await friend_challenges_notifications.send_deadline_notifications(
        now_utc=datetime.now(timezone.utc),
        reminder_items=[],
        expired_items=[
            {
                "challenge_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "creator_user_id": 10,
                "opponent_user_id": None,
                "creator_score": 0,
                "opponent_score": 0,
                "status": "EXPIRED",
                "previous_status": "PENDING",
            }
        ],
    )

    assert len(bot.sent_messages) == 1
    message = bot.sent_messages[0]
    assert message["text"] == "\n\n".join(
        [
            TEXTS_DE["msg.friend.challenge.reminder.unplayed"],
            TEXTS_DE["msg.friend.challenge.reminder.wait_or_close_hint"],
        ]
    )
    reply_markup = message["reply_markup"]
    assert isinstance(reply_markup, InlineKeyboardMarkup)
    buttons = [button for row in reply_markup.inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert [button.text for button in buttons] == ["⏳ Weiter warten", "❌ Schließen"]
    assert callbacks == [
        "home:open",
        "friend:delete:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    ]
    assert "friend:open:repost:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" not in callbacks


@pytest.mark.asyncio
async def test_send_deadline_notifications_unplayed_reminder_offers_arena_publish(
    monkeypatch,
) -> None:
    bot = _RecordingBot()

    async def _fake_resolve_targets(user_ids):
        return {user_id: user_id for user_id in user_ids}

    monkeypatch.setattr(friend_challenges_notifications, "build_bot", lambda: bot)
    monkeypatch.setattr(
        friend_challenges_notifications,
        "resolve_telegram_targets",
        _fake_resolve_targets,
    )

    await friend_challenges_notifications.send_deadline_notifications(
        now_utc=datetime.now(timezone.utc),
        reminder_items=[
            {
                "challenge_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "target_user_id": 10,
                "creator_user_id": 10,
                "opponent_user_id": None,
                "status": "PENDING",
                "expires_at": datetime(2026, 5, 5, 13, 0, tzinfo=timezone.utc),
                "reminder_kind": "unplayed",
            }
        ],
        expired_items=[],
    )

    assert len(bot.sent_messages) == 1
    message = bot.sent_messages[0]
    assert message["text"] == "\n\n".join(
        [
            TEXTS_DE["msg.friend.challenge.reminder.unplayed"],
            TEXTS_DE["msg.friend.challenge.reminder.publish_hint"],
        ]
    )
    reply_markup = message["reply_markup"]
    assert isinstance(reply_markup, InlineKeyboardMarkup)
    buttons = [button for row in reply_markup.inline_keyboard for button in row]
    assert [button.text for button in buttons] == [
        "🏟 In der Arena veröffentlichen",
        "⏳ Weiter warten",
        "❌ Schließen",
    ]
    assert [button.callback_data for button in buttons if button.callback_data] == [
        "arena:publish_friend:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "home:open",
        "friend:delete:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    ]
