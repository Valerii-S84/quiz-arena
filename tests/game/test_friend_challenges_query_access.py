from __future__ import annotations

import pytest

from app.game.sessions.service import friend_challenges_queries
from tests.game.friend_challenges_queries_test_support import (
    NOW_UTC,
    FriendChallengeQueriesSession,
    async_return,
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
async def test_list_friend_challenges_for_user_expires_rows_and_builds_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_open = build_challenge(status="ACTIVE", opponent_user_id=None)
    active_direct = build_challenge(status="ACTIVE", opponent_user_id=22)
    expired_events: list[dict[str, object]] = []

    def _fake_expire(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        if challenge is active_open:
            challenge.status = "EXPIRED"
            return True
        return False

    async def _fake_emit_expired_event(*_args, **kwargs) -> None:
        expired_events.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_queries.FriendChallengesRepo,
        "list_recent_for_user",
        async_return([active_open, active_direct]),
    )
    monkeypatch.setattr(friend_challenges_queries, "_expire_friend_challenge_if_due", _fake_expire)
    monkeypatch.setattr(
        friend_challenges_queries,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )
    monkeypatch.setattr(
        friend_challenges_queries,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: {
            "challenge_id": str(challenge_row.id),
            "status": challenge_row.status,
        },
    )

    result = await friend_challenges_queries.list_friend_challenges_for_user(
        FriendChallengeQueriesSession(),
        user_id=11,
        now_utc=NOW_UTC,
        limit=5,
    )

    assert result == [
        {"challenge_id": str(active_open.id), "status": "EXPIRED"},
        {"challenge_id": str(active_direct.id), "status": "ACCEPTED"},
    ]
    assert expired_events == [
        {
            "challenge": active_open,
            "happened_at": NOW_UTC,
            "source": friend_challenges_queries.EVENT_SOURCE_BOT,
        }
    ]
