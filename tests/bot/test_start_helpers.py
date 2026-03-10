from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import start_helpers
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import FriendChallengeSnapshot
from tests.bot.helpers import DummyBot, DummyMessage, DummySessionLocal


def _challenge_snapshot() -> FriendChallengeSnapshot:
    return FriendChallengeSnapshot(
        challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        invite_token="token",
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        status="ACCEPTED",
        creator_user_id=10,
        opponent_user_id=20,
        current_round=1,
        total_rounds=5,
        creator_score=0,
        opponent_score=0,
        winner_user_id=None,
    )


@pytest.mark.asyncio
async def test_notify_creator_about_join_sends_single_play_cta(monkeypatch) -> None:
    monkeypatch.setattr(start_helpers, "SessionLocal", DummySessionLocal())

    async def _fake_get_by_id_for_update(session, challenge_id):
        del session, challenge_id
        return SimpleNamespace(
            creator_user_id=10,
            creator_answered_round=0,
            total_rounds=5,
            creator_push_count=0,
            updated_at=None,
        )

    async def _fake_get_user(session, user_id):
        del session
        assert user_id == 10
        return SimpleNamespace(telegram_user_id=777)

    monkeypatch.setattr(
        start_helpers.FriendChallengesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )
    monkeypatch.setattr(start_helpers.UserOnboardingService, "get_by_id", _fake_get_user)

    message = DummyMessage(bot=DummyBot())
    await start_helpers._notify_creator_about_join(
        message,
        challenge=_challenge_snapshot(),
        joiner_user_id=20,
    )

    assert len(message.bot.sent_messages) == 1
    sent = message.bot.sent_messages[0]
    assert sent["chat_id"] == 777
    assert sent["text"] == TEXTS_DE["msg.friend.challenge.opponent.ready"]
    assert sent["reply_markup"].inline_keyboard[0][0].callback_data == (
        "friend:next:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    )


@pytest.mark.asyncio
async def test_notify_creator_about_join_skips_when_creator_already_finished(
    monkeypatch,
) -> None:
    monkeypatch.setattr(start_helpers, "SessionLocal", DummySessionLocal())

    async def _fake_get_by_id_for_update(session, challenge_id):
        del session, challenge_id
        return SimpleNamespace(
            creator_user_id=10,
            creator_answered_round=5,
            total_rounds=5,
            creator_push_count=0,
            updated_at=None,
        )

    monkeypatch.setattr(
        start_helpers.FriendChallengesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )

    message = DummyMessage(bot=DummyBot())
    await start_helpers._notify_creator_about_join(
        message,
        challenge=_challenge_snapshot(),
        joiner_user_id=20,
    )

    assert message.bot.sent_messages == []
