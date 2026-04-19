from __future__ import annotations

import pytest

from app.game.sessions.service import friend_challenges_queries
from tests.game.friend_challenges_queries_test_support import (
    NOW_UTC,
    FriendChallengeQueriesSession,
    build_challenge,
)


@pytest.mark.asyncio
async def test_get_friend_challenge_snapshot_for_user_delegates_to_shared_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_challenge()
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
    snapshot = {"challenge_id": str(challenge.id), "status": "EXPIRED"}
    monkeypatch.setattr(
        friend_challenges_queries,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: snapshot if challenge_row is challenge else None,
    )

    result = await friend_challenges_queries.get_friend_challenge_snapshot_for_user(
        session,
        user_id=11,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result == snapshot
    assert captured_kwargs == {
        "session": session,
        "user_id": 11,
        "challenge_id": challenge.id,
        "now_utc": NOW_UTC,
    }


@pytest.mark.asyncio
async def test_list_friend_challenges_for_user_delegates_to_query_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    session = FriendChallengeQueriesSession()

    async def _fake_list_friend_challenges_for_user(session, **kwargs):
        captured_kwargs["session"] = session
        captured_kwargs.update(kwargs)
        return [{"challenge_id": "first"}, {"challenge_id": "second"}]

    monkeypatch.setattr(
        friend_challenges_queries,
        "load_friend_challenge_snapshots_for_user",
        _fake_list_friend_challenges_for_user,
    )

    result = await friend_challenges_queries.list_friend_challenges_for_user(
        session,
        user_id=11,
        now_utc=NOW_UTC,
        limit=5,
    )

    assert result == [{"challenge_id": "first"}, {"challenge_id": "second"}]
    assert captured_kwargs == {
        "session": session,
        "user_id": 11,
        "now_utc": NOW_UTC,
        "limit": 5,
    }
