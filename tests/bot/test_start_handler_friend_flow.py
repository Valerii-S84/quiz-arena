from __future__ import annotations

from tests.bot.start_handler_flow_support import (
    TEXTS_DE,
    DummySessionLocal,
    FriendChallengeExpiredError,
    FriendChallengeNotFoundError,
    SimpleNamespace,
    _StartMessage,
)
from tests.bot.start_handler_flow_support import (  # noqa: F401
    _stub_start_runtime as _stub_start_runtime,
)
from tests.bot.start_handler_flow_support import duel_rollout, pytest, start

pytestmark = pytest.mark.usefixtures("_stub_start_runtime")


@pytest.mark.asyncio
async def test_handle_start_rejects_missing_user() -> None:
    message = _StartMessage(text="/start", from_user=None)

    await start.handle_start(message)  # type: ignore[arg-type]

    assert message.answers[0].text == TEXTS_DE["msg.system.error"]


@pytest.mark.asyncio
async def test_handle_start_friend_token_invalid(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(user_id=7, free_energy=10, paid_energy=0, current_streak=1)

    async def _fake_join_friend_challenge(*args, **kwargs):
        raise FriendChallengeNotFoundError()

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        start.GameSessionService,
        "join_friend_challenge_by_token",
        _fake_join_friend_challenge,
    )

    message = _StartMessage(
        text="/start fc_0123456789abcdef0123456789abcdef",
        from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="de"),
    )
    await start.handle_start(message)

    assert message.answers[0].text == TEXTS_DE["msg.friend.challenge.invalid"]


@pytest.mark.asyncio
async def test_handle_start_friend_token_expired(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(user_id=9, free_energy=10, paid_energy=0, current_streak=1)

    async def _fake_join_friend_challenge(*args, **kwargs):
        raise FriendChallengeExpiredError()

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        start.GameSessionService,
        "join_friend_challenge_by_token",
        _fake_join_friend_challenge,
    )

    message = _StartMessage(
        text="/start fc_0123456789abcdef0123456789abcdef",
        from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="de"),
    )
    await start.handle_start(message)

    assert message.answers[0].text == TEXTS_DE["msg.friend.challenge.expired"]


@pytest.mark.asyncio
async def test_handle_start_friend_payload_returns_disabled_guard_when_rollout_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(
        duel_rollout,
        "is_canonical_duels_enabled",
        lambda: False,
    )

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        assert start_payload == "fc_0123456789abcdef0123456789abcdef"
        return SimpleNamespace(user_id=9, free_energy=10, paid_energy=0, current_streak=1)

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)

    message = _StartMessage(
        text="/start fc_0123456789abcdef0123456789abcdef",
        from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="de"),
    )
    await start.handle_start(message)

    assert message.answers[0].text == TEXTS_DE["msg.duels.disabled"]
