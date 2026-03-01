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
