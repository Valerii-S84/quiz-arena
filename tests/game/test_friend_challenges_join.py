from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.game.sessions.service import friend_challenges_join, friend_challenges_join_state
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_join_friend_challenge_by_token_delegates_to_state_and_analytics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge()
    join_state = friend_challenges_join_state.FriendChallengeJoinState(
        challenge=challenge,
        joined_now=True,
    )
    load_calls: list[dict[str, object]] = []
    analytics_calls: list[dict[str, object]] = []

    async def _fake_load_joinable_friend_challenge_by_token(*_args, **kwargs):
        load_calls.append(kwargs)
        return join_state

    async def _fake_emit_friend_challenge_joined_events(*_args, **kwargs) -> None:
        analytics_calls.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_join,
        "load_joinable_friend_challenge_by_token",
        _fake_load_joinable_friend_challenge_by_token,
    )
    monkeypatch.setattr(
        friend_challenges_join,
        "emit_friend_challenge_joined_events",
        _fake_emit_friend_challenge_joined_events,
    )
    monkeypatch.setattr(
        friend_challenges_join,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: {"challenge_id": str(challenge_row.id)},
    )

    result = await friend_challenges_join.join_friend_challenge_by_token(
        _Session(),
        user_id=22,
        invite_token="invite-token",
        now_utc=NOW_UTC,
    )

    assert result.snapshot == {"challenge_id": str(challenge.id)}
    assert result.joined_now is True
    assert load_calls == [
        {
            "user_id": 22,
            "invite_token": "invite-token",
            "now_utc": NOW_UTC,
        }
    ]
    assert analytics_calls == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": friend_challenges_join.EVENT_SOURCE_BOT,
            "user_id": 22,
        }
    ]


@pytest.mark.asyncio
async def test_join_friend_challenge_by_id_returns_snapshot_without_analytics_when_not_joined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = build_friend_challenge()
    join_state = friend_challenges_join_state.FriendChallengeJoinState(
        challenge=challenge,
        joined_now=False,
    )
    load_calls: list[dict[str, object]] = []
    analytics_calls: list[dict[str, object]] = []

    async def _fake_load_joinable_friend_challenge_by_id(*_args, **kwargs):
        load_calls.append(kwargs)
        return join_state

    async def _fake_emit_friend_challenge_joined_events(*_args, **kwargs) -> None:
        analytics_calls.append(kwargs)

    snapshot = {"challenge_id": str(challenge.id), "joined_now": False}

    monkeypatch.setattr(
        friend_challenges_join,
        "load_joinable_friend_challenge_by_id",
        _fake_load_joinable_friend_challenge_by_id,
    )
    monkeypatch.setattr(
        friend_challenges_join,
        "emit_friend_challenge_joined_events",
        _fake_emit_friend_challenge_joined_events,
    )
    monkeypatch.setattr(
        friend_challenges_join,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: snapshot if challenge_row is challenge else None,
    )

    result = await friend_challenges_join.join_friend_challenge_by_id(
        _Session(),
        user_id=22,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert result.snapshot == snapshot
    assert result.joined_now is False
    assert load_calls == [
        {
            "user_id": 22,
            "challenge_id": challenge.id,
            "now_utc": NOW_UTC,
        }
    ]
    assert analytics_calls == []
