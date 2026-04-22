from __future__ import annotations

from uuid import uuid4

import pytest

from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.service import friend_challenges_queries
from tests.game.friend_challenges_queries_test_support import (
    NOW_UTC,
    FriendChallengeQueriesSession,
    async_return,
    build_challenge,
)


@pytest.mark.asyncio
async def test_get_friend_series_score_for_user_returns_default_for_non_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_challenge(series_id=None, series_best_of=1)

    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_queries,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    result = await friend_challenges_queries.get_friend_series_score_for_user(
        FriendChallengeQueriesSession(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == (0, 0, 1, 1)


@pytest.mark.asyncio
async def test_get_friend_series_score_for_user_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_queries.get_friend_series_score_for_user(
            FriendChallengeQueriesSession(),
            user_id=11,
            challenge_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_get_friend_series_score_for_user_swaps_perspective_for_opponent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series_id = uuid4()
    challenge = build_challenge(
        creator_user_id=11,
        opponent_user_id=22,
        series_id=series_id,
        series_game_number=3,
        series_best_of=5,
    )
    series_challenges = [
        build_challenge(
            status="COMPLETED",
            creator_user_id=11,
            opponent_user_id=22,
            series_id=series_id,
            winner_user_id=11,
        ),
        build_challenge(
            status="WALKOVER",
            creator_user_id=11,
            opponent_user_id=22,
            series_id=series_id,
            winner_user_id=22,
        ),
        build_challenge(
            status="ACCEPTED",
            creator_user_id=11,
            opponent_user_id=22,
            series_id=series_id,
            winner_user_id=22,
        ),
    ]

    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_queries,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "list_by_series_id_for_update",
        async_return(series_challenges),
    )

    result = await friend_challenges_queries.get_friend_series_score_for_user(
        FriendChallengeQueriesSession(),
        user_id=22,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == (1, 1, 3, 5)


@pytest.mark.asyncio
async def test_get_friend_series_score_for_user_emits_expired_event_before_access_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_challenge(
        status="ACTIVE",
        opponent_user_id=None,
        series_id=uuid4(),
        series_best_of=3,
    )
    expired_events: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = "EXPIRED"
        return True

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(challenge),
    )
    monkeypatch.setattr(friend_challenges_queries, "_expire_friend_challenge_if_due", _fake_expire)
    monkeypatch.setattr(
        friend_challenges_queries,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_queries.get_friend_series_score_for_user(
            FriendChallengeQueriesSession(),
            user_id=999,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )

    assert expired_events == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_queries.EVENT_SOURCE_BOT,
        }
    ]


@pytest.mark.asyncio
async def test_get_friend_series_score_for_user_returns_creator_perspective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series_id = uuid4()
    challenge = build_challenge(
        creator_user_id=11,
        opponent_user_id=22,
        series_id=series_id,
        series_game_number=2,
        series_best_of=3,
    )
    series_challenges = [
        build_challenge(
            status="COMPLETED",
            creator_user_id=11,
            opponent_user_id=22,
            series_id=series_id,
            winner_user_id=11,
        ),
        build_challenge(
            status="COMPLETED",
            creator_user_id=11,
            opponent_user_id=22,
            series_id=series_id,
            winner_user_id=22,
        ),
    ]

    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(challenge),
    )
    monkeypatch.setattr(
        friend_challenges_queries,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "list_by_series_id_for_update",
        async_return(series_challenges),
    )

    result = await friend_challenges_queries.get_friend_series_score_for_user(
        FriendChallengeQueriesSession(),
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == (1, 1, 2, 3)
