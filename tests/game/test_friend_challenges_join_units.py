from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.game.sessions.errors import (
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.service import friend_challenges_join
from tests.game.friend_challenges_unit_support import NOW_UTC, Session, async_return, challenge


@pytest.mark.asyncio
async def test_join_raises_when_challenge_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        friend_challenges_join.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_join.join_friend_challenge_by_id(
            Session(),
            user_id=22,
            challenge_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_join_raises_expired_after_emitting_event(monkeypatch: pytest.MonkeyPatch) -> None:
    row = challenge(opponent_user_id=None, status="PENDING")
    expired_events: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        challenge.status = "EXPIRED"
        challenge.updated_at = now_utc
        return True

    monkeypatch.setattr(
        friend_challenges_join.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )
    monkeypatch.setattr(friend_challenges_join, "_expire_friend_challenge_if_due", _fake_expire)
    monkeypatch.setattr(
        friend_challenges_join,
        "_emit_friend_challenge_expired_event",
        _append_async_kwargs(expired_events),
    )

    with pytest.raises(FriendChallengeExpiredError):
        await friend_challenges_join.join_friend_challenge_by_id(
            Session(),
            user_id=22,
            challenge_id=row.id,
            now_utc=NOW_UTC,
        )

    assert expired_events[0]["challenge"] is row


@pytest.mark.asyncio
async def test_join_returns_existing_creator_snapshot_without_joining(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(opponent_user_id=None, status="PENDING")
    monkeypatch.setattr(
        friend_challenges_join.FriendChallengesRepo,
        "get_by_invite_token_for_update",
        async_return(row),
    )

    result = await friend_challenges_join.join_friend_challenge_by_token(
        Session(),
        user_id=row.creator_user_id,
        invite_token=row.invite_token,
        now_utc=NOW_UTC,
    )

    assert result.joined_now is False
    assert result.snapshot.challenge_id == row.id
    assert result.snapshot.opponent_user_id is None


@pytest.mark.asyncio
async def test_join_sets_opponent_accepts_duel_and_emits_analytics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(opponent_user_id=None, status="PENDING")
    events: list[dict[str, object]] = []

    monkeypatch.setattr(
        friend_challenges_join.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )
    monkeypatch.setattr(
        friend_challenges_join,
        "_friend_challenge_expires_at_accepted",
        lambda **_kwargs: NOW_UTC + timedelta(hours=2),
    )
    monkeypatch.setattr(
        friend_challenges_join,
        "emit_analytics_event",
        _append_async_kwargs(events),
    )

    result = await friend_challenges_join.join_friend_challenge_by_id(
        Session(),
        user_id=22,
        challenge_id=row.id,
        now_utc=NOW_UTC,
    )

    assert result.joined_now is True
    assert row.opponent_user_id == 22
    assert row.status == "ACCEPTED"
    assert row.expires_at == NOW_UTC + timedelta(hours=2)
    assert events[0]["event_type"] == "friend_duel_joined"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "user_id", "expected_exc"),
    [
        ("COMPLETED", 22, FriendChallengeCompletedError),
        ("ACCEPTED", 33, FriendChallengeFullError),
    ],
)
async def test_join_rejects_completed_or_full_duel(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    user_id: int,
    expected_exc: type[Exception],
) -> None:
    row = challenge(status=status)
    monkeypatch.setattr(
        friend_challenges_join.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )

    with pytest.raises(expected_exc):
        await friend_challenges_join.join_friend_challenge_by_id(
            Session(),
            user_id=user_id,
            challenge_id=row.id,
            now_utc=NOW_UTC,
        )


def _append_async_kwargs(target: list[dict[str, object]]):
    async def _inner(*_args, **kwargs) -> None:
        target.append(kwargs)

    return _inner
