from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import friend_challenge_flow
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeLimitExceededError,
    FriendChallengePaymentRequiredError,
)
from tests.bot.helpers import DummyCallback, DummyMessage


class _SessionBegin:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _SessionLocal:
    def __init__(self, session: object) -> None:
        self._session = session

    def begin(self) -> _SessionBegin:
        return _SessionBegin(self._session)


@pytest.mark.asyncio
async def test_handle_friend_challenge_create_selected_rejects_invalid_context() -> None:
    callback = DummyCallback(
        data="friend:challenge:format:direct:5",
        from_user=None,
        message=DummyMessage(),
    )

    await friend_challenge_flow.handle_friend_challenge_create_selected(
        callback,
        session_local=SimpleNamespace(),
        user_onboarding_service=SimpleNamespace(),
        game_session_service=SimpleNamespace(),
        parse_challenge_rounds=lambda _data: 5,
        build_friend_invite_link=None,
        build_friend_plan_text=None,
        build_friend_ttl_text=None,
    )

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_friend_challenge_create_selected_rejects_unparseable_rounds() -> None:
    callback = DummyCallback(
        data="friend:challenge:format:direct:bad",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await friend_challenge_flow.handle_friend_challenge_create_selected(
        callback,
        session_local=SimpleNamespace(),
        user_onboarding_service=SimpleNamespace(),
        game_session_service=SimpleNamespace(),
        parse_challenge_rounds=lambda _data: None,
        build_friend_invite_link=None,
        build_friend_plan_text=None,
        build_friend_ttl_text=None,
    )

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_type",
    [FriendChallengePaymentRequiredError, FriendChallengeLimitExceededError],
)
async def test_handle_friend_challenge_create_selected_shows_limit_keyboard_on_create_error(
    exc_type,
) -> None:
    async def _fake_snapshot(_session, *, telegram_user):
        del _session
        assert telegram_user.id == 17
        return SimpleNamespace(user_id=99)

    async def _fake_create(*args, **kwargs):
        del args, kwargs
        raise exc_type

    callback = DummyCallback(
        data="friend:challenge:format:direct:5",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await friend_challenge_flow.handle_friend_challenge_create_selected(
        callback,
        session_local=_SessionLocal(object()),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_snapshot),
        game_session_service=SimpleNamespace(create_friend_challenge=_fake_create),
        parse_challenge_rounds=lambda _data: 5,
        build_friend_invite_link=None,
        build_friend_plan_text=None,
        build_friend_ttl_text=None,
    )

    assert callback.message.answers[0].text == TEXTS_DE["msg.friend.challenge.limit.reached"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_friend_challenge_create_selected_uses_fallback_text_without_ttl() -> None:
    session = object()
    captured: dict[str, object] = {}
    challenge_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    async def _fake_snapshot(_session, *, telegram_user):
        assert _session is session
        assert telegram_user.id == 17
        return SimpleNamespace(user_id=77)

    async def _fake_create(
        _session,
        *,
        creator_user_id: int,
        mode_code: str,
        now_utc,
        total_rounds: int,
    ):
        assert _session is session
        captured["creator_user_id"] = creator_user_id
        captured["mode_code"] = mode_code
        captured["total_rounds"] = total_rounds
        captured["now_utc"] = now_utc
        return SimpleNamespace(
            challenge_id=challenge_id,
            invite_token="invite-token",
            total_rounds=12,
        )

    async def _fake_invite_link(callback, *, invite_token: str):
        assert callback.from_user.id == 17
        assert invite_token == "invite-token"
        return None

    callback = DummyCallback(
        data="friend:challenge:format:direct:12",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await friend_challenge_flow.handle_friend_challenge_create_selected(
        callback,
        session_local=_SessionLocal(session),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_snapshot),
        game_session_service=SimpleNamespace(create_friend_challenge=_fake_create),
        parse_challenge_rounds=lambda data: 12 if data.endswith(":12") else None,
        build_friend_invite_link=_fake_invite_link,
        build_friend_plan_text=lambda *, total_rounds: f"plan:{total_rounds}",
        build_friend_ttl_text=lambda *, challenge, now_utc: None,
    )

    answer = callback.message.answers[0]
    assert captured == {
        "creator_user_id": 77,
        "mode_code": "QUICK_MIX_A1A2",
        "total_rounds": 12,
        "now_utc": captured["now_utc"],
    }
    assert TEXTS_DE["msg.friend.challenge.created.fallback"].format(
        invite_token="invite-token"
    ) in (answer.text or "")
    assert "plan:12" in (answer.text or "")
    assert TEXTS_DE["msg.friend.challenge.created.short"] in (answer.text or "")
    callbacks = [
        button.callback_data
        for row in answer.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert callbacks == ["friend:my:duels", "home:open"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
