from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay, gameplay_friend_challenge
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import FriendChallengeSnapshot
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_friend_open_repost_creates_new_open_duel_and_shows_share(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=17)

    async def _fake_repost(*args, **kwargs):
        return FriendChallengeSnapshot(
            challenge_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            invite_token="token",
            challenge_type="OPEN",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status="PENDING",
            creator_user_id=17,
            opponent_user_id=None,
            current_round=1,
            total_rounds=5,
            creator_score=0,
            opponent_score=0,
            winner_user_id=None,
        )

    async def _fake_invite_link(callback, *, challenge_id: str):
        del callback
        assert challenge_id == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        return "https://t.me/testbot?start=duel_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "repost_friend_challenge_as_open", _fake_repost)
    monkeypatch.setattr(gameplay, "_build_friend_invite_link", _fake_invite_link)

    callback = DummyCallback(
        data="friend:open:repost:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_friend_challenge.handle_friend_open_repost(callback)

    response = callback.message.answers[0]
    assert TEXTS_DE["msg.friend.challenge.created"] in (response.text or "")
    urls = [
        button.url
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.url
    ]
    assert len(urls) == 1
    assert "https://t.me/share/url" in (urls[0] or "")


@pytest.mark.asyncio
async def test_handle_friend_delete_marks_expired_challenge_deleted(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=17)

    async def _fake_delete(*args, **kwargs):
        del args, kwargs
        return None

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "cancel_friend_challenge_by_creator", _fake_delete)

    callback = DummyCallback(
        data="friend:delete:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_friend_challenge.handle_friend_delete(callback)

    assert callback.message.answers[0].text == TEXTS_DE["msg.friend.challenge.deleted"]
