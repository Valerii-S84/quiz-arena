from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import friend_challenge_flow
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeNotFoundError,
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
async def test_handle_friend_challenge_rematch_rejects_invalid_context() -> None:
    callback = DummyCallback(data="friend:rematch:any", from_user=None, message=DummyMessage())

    await friend_challenge_flow.handle_friend_challenge_rematch(
        callback,
        friend_rematch_re=object(),
        parse_uuid_callback=lambda **kwargs: UUID(int=0),
        session_local=SimpleNamespace(),
        user_onboarding_service=SimpleNamespace(),
        game_session_service=SimpleNamespace(),
        resolve_opponent_label=None,
        friend_opponent_user_id=None,
        notify_opponent=None,
        build_friend_plan_text=None,
        build_friend_ttl_text=None,
    )

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_friend_challenge_rematch_rejects_invalid_uuid() -> None:
    callback = DummyCallback(
        data="friend:rematch:not-a-uuid",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )

    await friend_challenge_flow.handle_friend_challenge_rematch(
        callback,
        friend_rematch_re=object(),
        parse_uuid_callback=lambda **kwargs: None,
        session_local=SimpleNamespace(),
        user_onboarding_service=SimpleNamespace(),
        game_session_service=SimpleNamespace(),
        resolve_opponent_label=None,
        friend_opponent_user_id=None,
        notify_opponent=None,
        build_friend_plan_text=None,
        build_friend_ttl_text=None,
    )

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_friend_challenge_rematch_notifies_opponent_on_success() -> None:
    session = object()
    challenge_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    calls: dict[str, object] = {}
    resolved_for: list[int] = []

    async def _fake_snapshot(_session, *, telegram_user):
        assert _session is session
        assert telegram_user.id == 17
        return SimpleNamespace(user_id=17)

    async def _fake_create_rematch(
        _session,
        *,
        initiator_user_id: int,
        challenge_id,
        now_utc,
    ):
        assert _session is session
        calls["initiator_user_id"] = initiator_user_id
        calls["challenge_id"] = challenge_id
        calls["now_utc"] = now_utc
        return SimpleNamespace(challenge_id=challenge_id, total_rounds=5)

    async def _fake_resolve_label(*, challenge, user_id: int):
        assert challenge.challenge_id == challenge_id
        resolved_for.append(user_id)
        return {17: "Bob", 99: "Alice"}[user_id]

    async def _fake_notify(callback, *, opponent_user_id: int, text: str, reply_markup) -> None:
        calls["notify_callback"] = callback
        calls["opponent_user_id"] = opponent_user_id
        calls["notify_text"] = text
        calls["notify_markup"] = reply_markup

    callback = DummyCallback(
        data=f"friend:rematch:{challenge_id}",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await friend_challenge_flow.handle_friend_challenge_rematch(
        callback,
        friend_rematch_re=object(),
        parse_uuid_callback=lambda **kwargs: challenge_id,
        session_local=_SessionLocal(session),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_snapshot),
        game_session_service=SimpleNamespace(create_friend_challenge_rematch=_fake_create_rematch),
        resolve_opponent_label=_fake_resolve_label,
        friend_opponent_user_id=lambda *, challenge, user_id: 99,
        notify_opponent=_fake_notify,
        build_friend_plan_text=lambda *, total_rounds: f"plan:{total_rounds}",
        build_friend_ttl_text=lambda *, challenge, now_utc: "ttl:active",
    )

    answer = callback.message.answers[0]
    assert calls["initiator_user_id"] == 17
    assert calls["challenge_id"] == challenge_id
    assert calls["notify_callback"] is callback
    assert calls["opponent_user_id"] == 99
    assert resolved_for == [17, 99]
    assert TEXTS_DE["msg.friend.challenge.rematch.created"].format(opponent_label="Bob") in (
        answer.text or ""
    )
    assert "plan:5" in (answer.text or "")
    assert "ttl:active" in (answer.text or "")
    assert TEXTS_DE["msg.friend.challenge.rematch.invite"].format(opponent_label="Alice") in str(
        calls["notify_text"]
    )
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_friend_challenge_rematch_shows_limit_keyboard_on_payment_required() -> None:
    async def _fake_snapshot(_session, *, telegram_user):
        del _session
        assert telegram_user.id == 17
        return SimpleNamespace(user_id=17)

    async def _fake_create_rematch(*args, **kwargs):
        del args, kwargs
        raise FriendChallengePaymentRequiredError

    callback = DummyCallback(
        data="friend:rematch:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await friend_challenge_flow.handle_friend_challenge_rematch(
        callback,
        friend_rematch_re=object(),
        parse_uuid_callback=lambda **kwargs: UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        session_local=_SessionLocal(object()),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_snapshot),
        game_session_service=SimpleNamespace(create_friend_challenge_rematch=_fake_create_rematch),
        resolve_opponent_label=None,
        friend_opponent_user_id=None,
        notify_opponent=None,
        build_friend_plan_text=None,
        build_friend_ttl_text=None,
    )

    assert callback.message.answers[0].text == TEXTS_DE["msg.friend.challenge.limit.reached"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
@pytest.mark.parametrize("exc_type", [FriendChallengeNotFoundError, FriendChallengeAccessError])
async def test_handle_friend_challenge_rematch_maps_not_found_and_access_errors(exc_type) -> None:
    async def _fake_snapshot(_session, *, telegram_user):
        del _session
        assert telegram_user.id == 17
        return SimpleNamespace(user_id=17)

    async def _fake_create_rematch(*args, **kwargs):
        del args, kwargs
        raise exc_type

    callback = DummyCallback(
        data="friend:rematch:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await friend_challenge_flow.handle_friend_challenge_rematch(
        callback,
        friend_rematch_re=object(),
        parse_uuid_callback=lambda **kwargs: UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        session_local=_SessionLocal(object()),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_snapshot),
        game_session_service=SimpleNamespace(create_friend_challenge_rematch=_fake_create_rematch),
        resolve_opponent_label=None,
        friend_opponent_user_id=None,
        notify_opponent=None,
        build_friend_plan_text=None,
        build_friend_ttl_text=None,
    )

    assert callback.message.answers[0].text == TEXTS_DE["msg.friend.challenge.invalid"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_friend_challenge_rematch_skips_notify_when_no_opponent_user_id() -> None:
    resolved_for: list[int] = []
    notify_called = False
    challenge_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    async def _fake_snapshot(_session, *, telegram_user):
        del _session
        assert telegram_user.id == 17
        return SimpleNamespace(user_id=17)

    async def _fake_create_rematch(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(challenge_id=challenge_id, total_rounds=5)

    async def _fake_resolve_label(*, challenge, user_id: int):
        assert challenge.challenge_id == challenge_id
        resolved_for.append(user_id)
        return "Bob"

    async def _fake_notify(*args, **kwargs) -> None:
        del args, kwargs
        nonlocal notify_called
        notify_called = True

    callback = DummyCallback(
        data=f"friend:rematch:{challenge_id}",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await friend_challenge_flow.handle_friend_challenge_rematch(
        callback,
        friend_rematch_re=object(),
        parse_uuid_callback=lambda **kwargs: challenge_id,
        session_local=_SessionLocal(object()),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_snapshot),
        game_session_service=SimpleNamespace(create_friend_challenge_rematch=_fake_create_rematch),
        resolve_opponent_label=_fake_resolve_label,
        friend_opponent_user_id=lambda *, challenge, user_id: None,
        notify_opponent=_fake_notify,
        build_friend_plan_text=lambda *, total_rounds: f"plan:{total_rounds}",
        build_friend_ttl_text=lambda *, challenge, now_utc: None,
    )

    assert resolved_for == [17]
    assert notify_called is False
    assert "plan:5" in (callback.message.answers[0].text or "")
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
