from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_EXPIRED
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.service import friend_challenges_manage_state
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _challenge(
    *,
    status: str = DUEL_STATUS_EXPIRED,
    creator_user_id: int = 11,
    opponent_user_id: int | None = 22,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        status=status,
    )


@pytest.mark.asyncio
async def test_load_manageable_friend_challenge_raises_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_manage_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_manage_state.load_manageable_friend_challenge(
            _Session(),
            user_id=11,
            challenge_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("challenge", "user_id"),
    [
        (_challenge(creator_user_id=11), 999),
        (_challenge(status="ACCEPTED", creator_user_id=11), 11),
    ],
)
async def test_load_manageable_friend_challenge_rejects_access_checks(
    monkeypatch: pytest.MonkeyPatch,
    challenge: SimpleNamespace,
    user_id: int,
) -> None:
    monkeypatch.setattr(
        friend_challenges_manage_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_manage_state.load_manageable_friend_challenge(
            _Session(),
            user_id=user_id,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_load_manageable_friend_challenge_emits_expired_event_before_access_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(status="ACTIVE", creator_user_id=11, opponent_user_id=None)
    expired_events: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = DUEL_STATUS_EXPIRED
        return True

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_manage_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage_state,
        "_expire_friend_challenge_if_due",
        _fake_expire,
    )
    monkeypatch.setattr(
        friend_challenges_manage_state,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_manage_state.load_manageable_friend_challenge(
            _Session(),
            user_id=999,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )

    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_manage_state.EVENT_SOURCE_BOT,
        }
    ]


@pytest.mark.asyncio
async def test_load_manageable_friend_challenge_returns_expired_creator_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()

    monkeypatch.setattr(
        friend_challenges_manage_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    result = await friend_challenges_manage_state.load_manageable_friend_challenge(
        _Session(),
        user_id=challenge.creator_user_id,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result is challenge


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
