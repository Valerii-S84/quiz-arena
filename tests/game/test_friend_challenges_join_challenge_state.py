from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED, DUEL_STATUS_PENDING
from app.game.sessions.errors import (
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.service import friend_challenges_join_challenge_state
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_load_joinable_friend_challenge_locked_raises_when_not_found() -> None:
    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_join_challenge_state.load_joinable_friend_challenge_locked(
            _Session(),
            user_id=11,
            challenge=None,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_load_joinable_friend_challenge_locked_emits_expired_event_before_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(status=DUEL_STATUS_PENDING, opponent_user_id=None)
    expired_events: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = "EXPIRED"
        return True

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_join_challenge_state,
        "_expire_friend_challenge_if_due",
        _fake_expire,
    )
    monkeypatch.setattr(
        friend_challenges_join_challenge_state,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )

    with pytest.raises(FriendChallengeExpiredError):
        await friend_challenges_join_challenge_state.load_joinable_friend_challenge_locked(
            _Session(),
            user_id=11,
            challenge=challenge,
            now_utc=NOW_UTC,
        )

    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_join_challenge_state.EVENT_SOURCE_BOT,
        }
    ]


@pytest.mark.asyncio
async def test_load_joinable_friend_challenge_locked_rejects_completed_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(status="CANCELED")

    monkeypatch.setattr(
        friend_challenges_join_challenge_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeCompletedError):
        await friend_challenges_join_challenge_state.load_joinable_friend_challenge_locked(
            _Session(),
            user_id=11,
            challenge=challenge,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_load_joinable_friend_challenge_locked_returns_creator_without_joining(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(
        creator_user_id=11,
        opponent_user_id=22,
        status=DUEL_STATUS_ACCEPTED,
    )

    monkeypatch.setattr(
        friend_challenges_join_challenge_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    result = await friend_challenges_join_challenge_state.load_joinable_friend_challenge_locked(
        _Session(),
        user_id=11,
        challenge=challenge,
        now_utc=NOW_UTC,
    )

    assert result == friend_challenges_join_challenge_state.FriendChallengeJoinState(
        challenge=challenge,
        joined_now=False,
    )


@pytest.mark.asyncio
async def test_load_joinable_friend_challenge_locked_accepts_open_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(
        creator_user_id=11,
        opponent_user_id=None,
        status=DUEL_STATUS_PENDING,
        expires_at=NOW_UTC - timedelta(minutes=5),
    )
    accepted_expires_at = NOW_UTC + timedelta(hours=6)

    monkeypatch.setattr(
        friend_challenges_join_challenge_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        friend_challenges_join_challenge_state,
        "_friend_challenge_expires_at_accepted",
        lambda **_kwargs: accepted_expires_at,
    )

    result = await friend_challenges_join_challenge_state.load_joinable_friend_challenge_locked(
        _Session(),
        user_id=33,
        challenge=challenge,
        now_utc=NOW_UTC,
    )

    assert result == friend_challenges_join_challenge_state.FriendChallengeJoinState(
        challenge=challenge,
        joined_now=True,
    )
    assert challenge.opponent_user_id == 33
    assert challenge.status == DUEL_STATUS_ACCEPTED
    assert challenge.expires_at == accepted_expires_at
    assert challenge.updated_at == NOW_UTC


@pytest.mark.asyncio
async def test_load_joinable_friend_challenge_locked_returns_existing_opponent_without_joining(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(opponent_user_id=22, status=DUEL_STATUS_ACCEPTED)

    monkeypatch.setattr(
        friend_challenges_join_challenge_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    result = await friend_challenges_join_challenge_state.load_joinable_friend_challenge_locked(
        _Session(),
        user_id=22,
        challenge=challenge,
        now_utc=NOW_UTC,
    )

    assert result == friend_challenges_join_challenge_state.FriendChallengeJoinState(
        challenge=challenge,
        joined_now=False,
    )


@pytest.mark.asyncio
async def test_load_joinable_friend_challenge_locked_rejects_when_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge(opponent_user_id=22, status=DUEL_STATUS_ACCEPTED)

    monkeypatch.setattr(
        friend_challenges_join_challenge_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeFullError):
        await friend_challenges_join_challenge_state.load_joinable_friend_challenge_locked(
            _Session(),
            user_id=44,
            challenge=challenge,
            now_utc=NOW_UTC,
        )
