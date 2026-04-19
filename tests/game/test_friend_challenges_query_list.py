from __future__ import annotations

import pytest

from app.game.sessions.service import friend_challenges_query_list
from tests.game.friend_challenges_queries_test_support import (
    NOW_UTC,
    FriendChallengeQueriesSession,
    async_return,
    build_challenge,
)


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
        friend_challenges_query_list.FriendChallengesRepo,
        "list_recent_for_user",
        async_return([active_open, active_direct]),
    )
    monkeypatch.setattr(
        friend_challenges_query_list,
        "_expire_friend_challenge_if_due",
        _fake_expire,
    )
    monkeypatch.setattr(
        friend_challenges_query_list,
        "_emit_friend_challenge_expired_event",
        _fake_emit_expired_event,
    )
    monkeypatch.setattr(
        friend_challenges_query_list,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: {
            "challenge_id": str(challenge_row.id),
            "status": challenge_row.status,
        },
    )

    result = await friend_challenges_query_list.list_friend_challenges_for_user(
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
            "source": friend_challenges_query_list.EVENT_SOURCE_BOT,
        }
    ]
