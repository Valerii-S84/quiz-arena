from __future__ import annotations

from uuid import uuid4

import pytest

from app.game.sessions.service import friend_challenges_queries
from tests.game.friend_challenges_queries_test_support import (
    NOW_UTC,
    FriendChallengeQueriesSession,
    async_return,
    build_challenge,
)


@pytest.mark.asyncio
async def test_get_friend_series_score_for_user_delegates_to_shared_loader_for_non_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_challenge(series_id=None, series_best_of=1)
    captured_kwargs: dict[str, object] = {}
    session = FriendChallengeQueriesSession()

    async def _fake_load_friend_challenge_for_user(session, **kwargs):
        captured_kwargs["session"] = session
        captured_kwargs.update(kwargs)
        return challenge

    monkeypatch.setattr(
        friend_challenges_queries,
        "load_friend_challenge_for_user",
        _fake_load_friend_challenge_for_user,
    )

    result = await friend_challenges_queries.get_friend_series_score_for_user(
        session,
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == (0, 0, 1, 1)
    assert captured_kwargs == {
        "session": session,
        "user_id": 11,
        "challenge_id": challenge.id,
        "now_utc": NOW_UTC,
    }


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
        friend_challenges_queries,
        "load_friend_challenge_for_user",
        async_return(challenge),
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
        friend_challenges_queries,
        "load_friend_challenge_for_user",
        async_return(challenge),
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
