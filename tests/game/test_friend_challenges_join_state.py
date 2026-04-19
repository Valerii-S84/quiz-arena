from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.game.sessions.service import (
    friend_challenges_join_challenge_state,
    friend_challenges_join_state,
)
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("loader_name", "repo_method_name", "loader_kwargs"),
    [
        (
            "load_joinable_friend_challenge_by_token",
            "get_by_invite_token_for_update",
            {"invite_token": "invite-token"},
        ),
        (
            "load_joinable_friend_challenge_by_id",
            "get_by_id_for_update",
            {"challenge_id": uuid4()},
        ),
    ],
    ids=["by_token", "by_id"],
)
async def test_join_state_loaders_delegate_to_locked_join_state(
    monkeypatch: pytest.MonkeyPatch,
    loader_name: str,
    repo_method_name: str,
    loader_kwargs: dict[str, object],
) -> None:
    session = _Session()
    challenge = build_friend_challenge()
    expected_state = friend_challenges_join_challenge_state.FriendChallengeJoinState(
        challenge=challenge,
        joined_now=True,
    )
    repo_calls: list[tuple[object, object]] = []
    locked_calls: list[dict[str, object]] = []

    async def _fake_repo_get(session, lookup_value):
        repo_calls.append((session, lookup_value))
        return challenge

    async def _fake_load_joinable_friend_challenge_locked(*args, **kwargs):
        locked_calls.append({"session": args[0], **kwargs})
        return expected_state

    monkeypatch.setattr(
        friend_challenges_join_state.FriendChallengesRepo,
        repo_method_name,
        _fake_repo_get,
    )
    monkeypatch.setattr(
        friend_challenges_join_state,
        "load_joinable_friend_challenge_locked",
        _fake_load_joinable_friend_challenge_locked,
    )

    result = await getattr(friend_challenges_join_state, loader_name)(
        session,
        user_id=11,
        now_utc=NOW_UTC,
        **loader_kwargs,
    )

    assert result is expected_state
    assert repo_calls == [(session, next(iter(loader_kwargs.values())))]
    assert locked_calls == [
        {
            "session": session,
            "user_id": 11,
            "challenge": challenge,
            "now_utc": NOW_UTC,
        }
    ]
