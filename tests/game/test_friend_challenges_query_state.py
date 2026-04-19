from __future__ import annotations

from uuid import uuid4

import pytest

from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.service import friend_challenges_query_state
from tests.game.friend_challenges_queries_test_support import (
    NOW_UTC,
    FriendChallengeQueriesSession,
    async_return,
    build_challenge,
)


@pytest.mark.asyncio
async def test_load_friend_challenge_for_user_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_query_state.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_query_state.load_friend_challenge_for_user(
            FriendChallengeQueriesSession(),
            user_id=11,
            challenge_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_load_friend_challenge_for_user_rejects_outsider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_challenge()

    monkeypatch.setattr(
        friend_challenges_query_state.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_query_state,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_query_state.load_friend_challenge_for_user(
            FriendChallengeQueriesSession(),
            user_id=999,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_load_friend_challenge_for_user_emits_expired_event_before_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_challenge(status="ACTIVE", opponent_user_id=None)
    expired_events: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = "EXPIRED"
        return True

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_query_state.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_query_state,
        "_expire_friend_challenge_if_due",
        _fake_expire,
    )
    monkeypatch.setattr(
        friend_challenges_query_state,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )

    result = await friend_challenges_query_state.load_friend_challenge_for_user(
        FriendChallengeQueriesSession(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result is challenge
    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_query_state.EVENT_SOURCE_BOT,
        }
    ]
