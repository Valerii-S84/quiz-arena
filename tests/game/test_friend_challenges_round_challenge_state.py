from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.friend_challenges.constants import DUEL_STATUS_EXPIRED, DUEL_STATUS_LEGACY_ACTIVE
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeExpiredError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.service import friend_challenges_round_challenge_state
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


def _challenge(**overrides: object) -> FriendChallenge:
    payload: dict[str, object] = {
        "mode_code": "QUICK_MIX_A1A2",
        "total_rounds": 7,
    }
    payload.update(overrides)
    return build_friend_challenge(**payload)


@pytest.mark.asyncio
async def test_load_round_friend_challenge_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_round_challenge_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_round_challenge_state.load_round_friend_challenge(
            _Session(),
            challenge_id=_challenge().id,
            user_id=10,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "expected_is_creator"),
    [(10, True), (20, False)],
    ids=["creator_access", "opponent_access"],
)
async def test_load_round_friend_challenge_normalizes_and_returns_access_context(
    monkeypatch: pytest.MonkeyPatch,
    user_id: int,
    expected_is_creator: bool,
) -> None:
    challenge = _challenge(
        status=DUEL_STATUS_LEGACY_ACTIVE,
        creator_user_id=10,
        opponent_user_id=20,
    )

    monkeypatch.setattr(
        friend_challenges_round_challenge_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_round_challenge_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    result = await friend_challenges_round_challenge_state.load_round_friend_challenge(
        _Session(),
        challenge_id=challenge.id,
        user_id=user_id,
        now_utc=NOW_UTC,
    )

    assert result == friend_challenges_round_challenge_state.FriendChallengeRoundChallengeState(
        challenge=challenge,
        has_opponent=True,
        is_creator=expected_is_creator,
    )
    assert challenge.status == "ACCEPTED"


@pytest.mark.asyncio
async def test_load_round_friend_challenge_emits_expired_event_before_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(status="PENDING", creator_user_id=10, opponent_user_id=None)
    expired_events: list[dict[str, object]] = []

    def _fake_expire(*, challenge: FriendChallenge, now_utc: datetime) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = DUEL_STATUS_EXPIRED
        return True

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_round_challenge_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_round_challenge_state,
        "_expire_friend_challenge_if_due",
        _fake_expire,
    )
    monkeypatch.setattr(
        friend_challenges_round_challenge_state,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )

    with pytest.raises(FriendChallengeExpiredError):
        await friend_challenges_round_challenge_state.load_round_friend_challenge(
            _Session(),
            challenge_id=challenge.id,
            user_id=10,
            now_utc=NOW_UTC,
        )

    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_round_challenge_state.EVENT_SOURCE_BOT,
        }
    ]


@pytest.mark.asyncio
async def test_load_round_friend_challenge_rejects_outsider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(status="ACCEPTED", creator_user_id=10, opponent_user_id=20)

    monkeypatch.setattr(
        friend_challenges_round_challenge_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_round_challenge_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_round_challenge_state.load_round_friend_challenge(
            _Session(),
            challenge_id=challenge.id,
            user_id=999,
            now_utc=NOW_UTC,
        )
