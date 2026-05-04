from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay, gameplay_friend_challenge
from app.bot.handlers.gameplay_flows import friend_lobby_flow
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import FriendChallengeSnapshot
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_friend_challenge_type_legacy_callback_redirects_to_canonical_duel_entry() -> (
    None
):
    callback = DummyCallback(
        data="friend:challenge:type:direct",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_friend_challenge.handle_friend_challenge_type_selected(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.duels.friend"]
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert callbacks == ["friend:challenge:format:direct:7", "duels:menu"]


@pytest.mark.asyncio
async def test_handle_friend_challenge_create_selected_sends_waiting_keyboard(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())
    captured: dict[str, object] = {}

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=17)

    async def _fake_create_friend_challenge(*args, **kwargs):
        del args
        captured.update(kwargs)
        return FriendChallengeSnapshot(
            challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            invite_token="token",
            challenge_type="DIRECT",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status="ACTIVE",
            creator_user_id=17,
            opponent_user_id=None,
            current_round=1,
            total_rounds=7,
            creator_score=0,
            opponent_score=0,
            winner_user_id=None,
        )

    async def _fake_build_invite_link(callback, *, challenge_id: str):
        del callback
        assert challenge_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        return "https://t.me/testbot?start=duel_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "create_friend_challenge",
        _fake_create_friend_challenge,
    )
    monkeypatch.setattr(gameplay, "_build_friend_invite_link", _fake_build_invite_link)
    monkeypatch.setattr(
        friend_lobby_flow,
        "get_settings",
        lambda: SimpleNamespace(resolved_welcome_image_file_id=""),
    )

    callback = DummyCallback(
        data="friend:challenge:format:direct:7",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_friend_challenge.handle_friend_challenge_create_selected(callback)

    invite_message = callback.message.answers[0]
    invite_buttons = [
        button for row in invite_message.kwargs["reply_markup"].inline_keyboard for button in row
    ]
    callbacks = [button.callback_data for button in invite_buttons if button.callback_data]
    assert captured["total_rounds"] == 7
    assert captured["challenge_type"] == "DIRECT"
    assert [button.text for button in invite_buttons] == [
        "📤 Teilen ->",
        "✅ Einladung gesendet",
        "⚔️ Jetzt spielen",
        "⏳ Auf Freund warten",
    ]
    assert "arena:publish_friend:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" not in callbacks
    assert not any(button.url and "duel_" in button.url for button in invite_buttons)
    assert len(callback.message.answers) == 1


@pytest.mark.asyncio
async def test_handle_friend_challenge_invite_sent_answers_with_waiting_toast() -> None:
    message = DummyMessage()
    callback = DummyCallback(
        data="friend:invite:sent:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=message,
    )
    await gameplay_friend_challenge.handle_friend_challenge_invite_sent(callback)

    assert callback.message.answers == []
    assert len(message.edit_reply_markup_calls) == 1
    edited_markup = message.edit_reply_markup_calls[0]["reply_markup"]
    edited_callbacks = [
        button.callback_data
        for row in edited_markup.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert edited_callbacks == [
        "friend:invite:sent:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "friend:next:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "menu:main",
    ]
    edited_buttons = [button for row in edited_markup.inline_keyboard for button in row]
    assert not any(button.url and "duel_" in button.url for button in edited_buttons)
    assert callback.answer_calls == [
        {"text": TEXTS_DE["msg.friend.challenge.invite.waiting"], "show_alert": False}
    ]


@pytest.mark.asyncio
async def test_handle_friend_challenge_invite_required_answers_with_confirmation_hint() -> None:
    callback = DummyCallback(
        data="friend:invite:required:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_friend_challenge.handle_friend_challenge_invite_required(callback)

    assert callback.answer_calls == [
        {"text": TEXTS_DE["msg.friend.challenge.invite.confirm.first"], "show_alert": False}
    ]


@pytest.mark.asyncio
async def test_handle_friend_my_duels_groups_sections_with_my_turn_first(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=17)

    now = datetime(2026, 2, 27, 18, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 2, 27, 17, 30, tzinfo=timezone.utc)

    async def _fake_list_duels(*args, **kwargs):
        return [
            FriendChallengeSnapshot(
                challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                invite_token="token-a",
                challenge_type="DIRECT",
                mode_code="QUICK_MIX_A1A2",
                access_type="FREE",
                status="CREATOR_DONE",
                creator_user_id=17,
                opponent_user_id=18,
                current_round=5,
                total_rounds=5,
                creator_score=3,
                opponent_score=1,
                creator_finished_at=finished_at,
                winner_user_id=None,
                expires_at=now,
            ),
            FriendChallengeSnapshot(
                challenge_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                invite_token="token-b",
                challenge_type="OPEN",
                mode_code="QUICK_MIX_A1A2",
                access_type="FREE",
                status="PENDING",
                creator_user_id=17,
                opponent_user_id=None,
                current_round=1,
                total_rounds=12,
                creator_score=0,
                opponent_score=0,
                winner_user_id=None,
                expires_at=now,
            ),
            FriendChallengeSnapshot(
                challenge_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
                invite_token="token-c",
                challenge_type="DIRECT",
                mode_code="QUICK_MIX_A1A2",
                access_type="FREE",
                status="ACCEPTED",
                creator_user_id=17,
                opponent_user_id=19,
                current_round=2,
                total_rounds=5,
                creator_score=1,
                opponent_score=1,
                winner_user_id=None,
                expires_at=now,
            ),
            FriendChallengeSnapshot(
                challenge_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
                invite_token="token-d",
                challenge_type="DIRECT",
                mode_code="QUICK_MIX_A1A2",
                access_type="FREE",
                status="COMPLETED",
                creator_user_id=17,
                opponent_user_id=20,
                current_round=5,
                total_rounds=5,
                creator_score=4,
                opponent_score=2,
                winner_user_id=17,
                expires_at=now,
            ),
        ]

    async def _fake_opponent_label(*, challenge, user_id):
        del user_id
        labels = {
            UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"): "Anna",
            UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"): "Freund",
            UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"): "Max",
            UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"): "Klaus",
        }
        return labels[challenge.challenge_id]

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService, "list_friend_challenges_for_user", _fake_list_duels
    )
    monkeypatch.setattr(gameplay, "_resolve_opponent_label", _fake_opponent_label)

    callback = DummyCallback(
        data="friend:my:duels",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay_friend_challenge.handle_friend_my_duels(callback)

    text = callback.message.answers[0].text or ""
    my_turn_pos = text.find(TEXTS_DE["msg.friend.challenge.my.my_turn"])
    waiting_pos = text.find(TEXTS_DE["msg.friend.challenge.my.waiting"])
    open_pos = text.find(TEXTS_DE["msg.friend.challenge.my.open"])
    completed_pos = text.find(TEXTS_DE["msg.friend.challenge.my.completed"])
    assert -1 not in {my_turn_pos, waiting_pos, completed_pos}
    assert open_pos == -1
    assert my_turn_pos < waiting_pos < completed_pos

    keyboard = callback.message.answers[0].kwargs["reply_markup"]
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "friend:next:cccccccc-cccc-cccc-cccc-cccccccccccc" in callbacks
    assert "friend:rematch:dddddddd-dddd-dddd-dddd-dddddddddddd" in callbacks
    assert "home:open" in callbacks
