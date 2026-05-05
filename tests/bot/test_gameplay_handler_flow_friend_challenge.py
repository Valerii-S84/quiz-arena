from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from app.game.duels import rollout as duel_rollout
from app.game.sessions.types import FriendChallengeSnapshot
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "callback_data"),
    [
        ("handle_friend_challenge_rematch", "friend:rematch:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    ],
)
async def test_follow_up_friend_duel_callbacks_are_blocked_when_rollout_is_off(
    monkeypatch: pytest.MonkeyPatch,
    handler_name: str,
    callback_data: str,
) -> None:
    monkeypatch.setattr(duel_rollout, "is_canonical_duels_enabled", lambda: False)
    callback = DummyCallback(
        data=callback_data,
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )

    await getattr(gameplay, handler_name)(callback)

    assert callback.message.answers[0].text == TEXTS_DE["msg.duels.disabled"]
    assert callback.message.answers[0].kwargs["reply_markup"] is not None
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_friend_challenge_rematch_creates_duel_and_notifies_opponent(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=10)

    async def _fake_rematch(*args, **kwargs):
        return FriendChallengeSnapshot(
            challenge_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            invite_token="token-rematch",
            challenge_type="DIRECT",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status="ACTIVE",
            creator_user_id=10,
            opponent_user_id=20,
            current_round=1,
            total_rounds=5,
            creator_score=0,
            opponent_score=0,
            winner_user_id=None,
        )

    notified: list[int] = []

    async def _fake_notify(callback, *, opponent_user_id, text, reply_markup=None):
        del callback, text, reply_markup
        notified.append(opponent_user_id)

    async def _fake_resolve_label(*, challenge, user_id):
        del challenge
        return "Bob" if user_id == 10 else "Alice"

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService, "create_friend_challenge_rematch", _fake_rematch
    )
    monkeypatch.setattr(gameplay, "_notify_opponent", _fake_notify)
    monkeypatch.setattr(gameplay, "_resolve_opponent_label", _fake_resolve_label)

    callback = DummyCallback(
        data="friend:rematch:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_rematch(callback)

    response = callback.message.answers[0]
    assert TEXTS_DE["msg.friend.challenge.rematch.created"].format(opponent_label="Bob") in (
        response.text or ""
    )
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "friend:next:cccccccc-cccc-cccc-cccc-cccccccccccc" in callbacks
    assert notified == [20]
