from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.service import friend_challenges_rounds
from tests.game.friend_challenges_unit_support import NOW_UTC, Session, async_return, challenge


@pytest.mark.asyncio
async def test_round_start_raises_when_challenge_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        friend_challenges_rounds.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_rounds.start_friend_challenge_round(
            Session(),
            user_id=11,
            challenge_id=uuid4(),
            idempotency_key="round:missing",
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_round_start_expires_due_challenge(monkeypatch: pytest.MonkeyPatch) -> None:
    row = challenge(status="PENDING", opponent_user_id=None)
    row.expires_at = NOW_UTC - timedelta(seconds=1)
    expired_events: list[dict[str, object]] = []

    monkeypatch.setattr(
        friend_challenges_rounds.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )
    monkeypatch.setattr(
        friend_challenges_rounds,
        "_emit_friend_challenge_expired_event",
        _append_kwargs(expired_events),
    )

    with pytest.raises(FriendChallengeExpiredError):
        await friend_challenges_rounds.start_friend_challenge_round(
            Session(),
            user_id=11,
            challenge_id=row.id,
            idempotency_key="round:expired",
            now_utc=NOW_UTC,
        )

    assert expired_events[0]["challenge"] is row


@pytest.mark.asyncio
async def test_round_start_rejects_non_participant(monkeypatch: pytest.MonkeyPatch) -> None:
    row = challenge()
    monkeypatch.setattr(
        friend_challenges_rounds.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_rounds.start_friend_challenge_round(
            Session(),
            user_id=999,
            challenge_id=row.id,
            idempotency_key="round:outsider",
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_round_start_rejects_finished_duel(monkeypatch: pytest.MonkeyPatch) -> None:
    row = challenge(status="COMPLETED")
    monkeypatch.setattr(
        friend_challenges_rounds.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )

    with pytest.raises(FriendChallengeCompletedError):
        await friend_challenges_rounds.start_friend_challenge_round(
            Session(),
            user_id=11,
            challenge_id=row.id,
            idempotency_key="round:completed",
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_round_start_rejects_closed_duel_without_opponent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(status="CANCELED", opponent_user_id=None)
    monkeypatch.setattr(
        friend_challenges_rounds.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )

    with pytest.raises(FriendChallengeFullError):
        await friend_challenges_rounds.start_friend_challenge_round(
            Session(),
            user_id=11,
            challenge_id=row.id,
            idempotency_key="round:full",
            now_utc=NOW_UTC,
        )


def _append_kwargs(target: list[dict[str, object]]):
    async def _inner(*_args, **kwargs) -> None:
        target.append(kwargs)

    return _inner
