from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.friend_challenges.constants import (
    DUEL_STATUS_CANCELED,
    DUEL_STATUS_COMPLETED,
    DUEL_STATUS_EXPIRED,
    DUEL_STATUS_LEGACY_ACTIVE,
)
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.service import friend_challenges_rounds_state
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
async def test_load_friend_challenge_round_context_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_rounds_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_rounds_state.load_friend_challenge_round_context(
            _Session(),
            challenge_id=_challenge().id,
            user_id=10,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_load_friend_challenge_round_context_normalizes_status_and_computes_next_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(
        status=DUEL_STATUS_LEGACY_ACTIVE,
        creator_user_id=10,
        opponent_user_id=20,
        creator_answered_round=1,
    )
    monkeypatch.setattr(
        friend_challenges_rounds_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_rounds_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    context = await friend_challenges_rounds_state.load_friend_challenge_round_context(
        _Session(),
        challenge_id=challenge.id,
        user_id=10,
        now_utc=NOW_UTC,
    )

    assert context.challenge is challenge
    assert challenge.status == "ACCEPTED"
    assert context.has_opponent is True
    assert context.is_creator is True
    assert context.next_round == 2


@pytest.mark.asyncio
async def test_load_friend_challenge_round_context_emits_expired_event_before_expired_error(
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
        friend_challenges_rounds_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_rounds_state,
        "_expire_friend_challenge_if_due",
        _fake_expire,
    )
    monkeypatch.setattr(
        friend_challenges_rounds_state,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )

    with pytest.raises(FriendChallengeExpiredError):
        await friend_challenges_rounds_state.load_friend_challenge_round_context(
            _Session(),
            challenge_id=challenge.id,
            user_id=10,
            now_utc=NOW_UTC,
        )

    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_rounds_state.EVENT_SOURCE_BOT,
        }
    ]


@pytest.mark.asyncio
async def test_load_friend_challenge_round_context_rejects_outsider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(status="ACCEPTED", creator_user_id=10, opponent_user_id=20)
    monkeypatch.setattr(
        friend_challenges_rounds_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_rounds_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_rounds_state.load_friend_challenge_round_context(
            _Session(),
            challenge_id=challenge.id,
            user_id=999,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("challenge", "expected_error"),
    [
        (
            _challenge(
                status=DUEL_STATUS_CANCELED,
                creator_user_id=10,
                opponent_user_id=None,
            ),
            FriendChallengeFullError,
        ),
        (
            _challenge(
                status=DUEL_STATUS_COMPLETED,
                creator_user_id=10,
                opponent_user_id=20,
            ),
            FriendChallengeCompletedError,
        ),
    ],
    ids=["full_without_opponent", "completed_with_opponent"],
)
async def test_load_friend_challenge_round_context_rejects_non_playable_states(
    monkeypatch: pytest.MonkeyPatch,
    challenge: FriendChallenge,
    expected_error: type[Exception],
) -> None:
    monkeypatch.setattr(
        friend_challenges_rounds_state.FriendChallengesRepo,
        "get_by_id_for_update",
        _async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_rounds_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(expected_error):
        await friend_challenges_rounds_state.load_friend_challenge_round_context(
            _Session(),
            challenge_id=challenge.id,
            user_id=10,
            now_utc=NOW_UTC,
        )
