from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay
from app.bot.handlers.gameplay_flows import friend_lobby_flow
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import FriendChallengeSnapshot
from tests.bot.helpers import DummyBot, DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_friend_challenge_create_opens_format_picker(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    callback = DummyCallback(
        data="friend:challenge:create",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_create(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.friend.challenge.create.choose"]
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "friend:challenge:type:direct" in callbacks
    assert "friend:challenge:type:open" not in callbacks
    assert "friend:challenge:type:tournament" not in callbacks


@pytest.mark.asyncio
async def test_handle_friend_challenge_create_selected_hides_raw_url_and_keeps_share_link(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=17)

    async def _fake_create_friend_challenge(*args, **kwargs):
        return FriendChallengeSnapshot(
            challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            invite_token="0123456789abcdef0123456789abcdef",
            challenge_type="DIRECT",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status="ACTIVE",
            creator_user_id=17,
            opponent_user_id=None,
            current_round=1,
            total_rounds=5,
            creator_score=0,
            opponent_score=0,
            winner_user_id=None,
        )

    async def _fake_friend_invite_link(callback, *, challenge_id: str):
        assert challenge_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        return "https://t.me/testbot?start=duel_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "create_friend_challenge",
        _fake_create_friend_challenge,
    )
    monkeypatch.setattr(gameplay, "_build_friend_invite_link", _fake_friend_invite_link)
    monkeypatch.setattr(
        friend_lobby_flow,
        "get_settings",
        lambda: SimpleNamespace(resolved_welcome_image_file_id="welcome-file-id"),
    )

    callback = DummyCallback(
        data="friend:challenge:format:direct:5",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(bot=DummyBot()),
    )
    await gameplay.handle_friend_challenge_create_selected(callback)

    assert len(callback.bot.sent_photos) == 1
    assert callback.message.answers == []
    photo_call = callback.bot.sent_photos[0]
    assert photo_call["caption"] == TEXTS_DE["msg.friend.challenge.invite.caption"]
    keyboard = photo_call["reply_markup"]
    assert "https://t.me/" not in (photo_call["caption"] or "")
    assert "http" not in (photo_call["caption"] or "")
    assert keyboard is not None
    assert keyboard.inline_keyboard[0][0].text == "⚔️ Herausforderung annehmen"
    assert (
        keyboard.inline_keyboard[0][0].url
        == "https://t.me/testbot?start=duel_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    )
    inline_queries = [
        button.switch_inline_query
        for row in keyboard.inline_keyboard
        for button in row
        if button.switch_inline_query
    ]
    assert inline_queries == ["invite:duel:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert callbacks == [
        "friend:invite:sent:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "friend:invite:required:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "menu:main",
    ]
