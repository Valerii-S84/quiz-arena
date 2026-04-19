from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeLimitExceededError
from app.game.sessions.service import friend_challenges_create_limits
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


@pytest.mark.asyncio
async def test_resolve_create_request_rejects_invalid_challenge_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_count_live(*args, **kwargs):
        del args, kwargs
        pytest.fail("repo lookups should not run for an invalid challenge type")

    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_live_for_user",
        _unexpected_count_live,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_create_limits.resolve_friend_challenge_create_request(
            _Session(),
            creator_user_id=101,
            challenge_type="PRIVATE",
            total_rounds=12,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_resolve_create_request_rejects_active_duel_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(friend_challenges_create_limits, "DUEL_MAX_ACTIVE_PER_USER", 2)
    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_live_for_user",
        _async_return(2),
    )

    async def _unexpected_open_count(*args, **kwargs):
        del args, kwargs
        pytest.fail("open count should not run after active limit rejection")

    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_live_open_by_creator",
        _unexpected_open_count,
    )

    with pytest.raises(FriendChallengeLimitExceededError):
        await friend_challenges_create_limits.resolve_friend_challenge_create_request(
            _Session(),
            creator_user_id=101,
            challenge_type="DIRECT",
            total_rounds=12,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_resolve_create_request_rejects_existing_open_duel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_live_for_user",
        _async_return(0),
    )
    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_live_open_by_creator",
        _async_return(1),
    )

    async def _unexpected_created_today(*args, **kwargs):
        del args, kwargs
        pytest.fail("created-today count should not run after open limit rejection")

    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_created_since",
        _unexpected_created_today,
    )

    with pytest.raises(FriendChallengeLimitExceededError):
        await friend_challenges_create_limits.resolve_friend_challenge_create_request(
            _Session(),
            creator_user_id=101,
            challenge_type="OPEN",
            total_rounds=12,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_resolve_create_request_rejects_daily_create_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(friend_challenges_create_limits, "DUEL_MAX_NEW_PER_DAY", 3)
    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_live_for_user",
        _async_return(0),
    )

    async def _unexpected_open_count(*args, **kwargs):
        del args, kwargs
        pytest.fail("open count should not run for a direct challenge")

    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_live_open_by_creator",
        _unexpected_open_count,
    )
    monkeypatch.setattr(
        friend_challenges_create_limits,
        "berlin_day_start_utc",
        lambda **_: NOW_UTC,
    )
    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_created_since",
        _async_return(3),
    )

    with pytest.raises(FriendChallengeLimitExceededError):
        await friend_challenges_create_limits.resolve_friend_challenge_create_request(
            _Session(),
            creator_user_id=101,
            challenge_type="DIRECT",
            total_rounds=12,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_resolve_create_request_returns_direct_request_without_open_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        friend_challenges_create_limits,
        "resolve_duel_rounds",
        lambda **_: 5,
    )
    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_live_for_user",
        _async_return(0),
    )

    async def _unexpected_open_count(*args, **kwargs):
        del args, kwargs
        pytest.fail("open count should not run for a direct challenge")

    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_live_open_by_creator",
        _unexpected_open_count,
    )
    monkeypatch.setattr(
        friend_challenges_create_limits,
        "berlin_day_start_utc",
        lambda **_: NOW_UTC,
    )

    async def _fake_count_created_since(*args, **kwargs):
        del args
        captured["kwargs"] = kwargs
        return 0

    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_created_since",
        _fake_count_created_since,
    )

    request = await friend_challenges_create_limits.resolve_friend_challenge_create_request(
        _Session(),
        creator_user_id=101,
        challenge_type="DIRECT",
        total_rounds=12,
        now_utc=NOW_UTC,
    )

    assert request == friend_challenges_create_limits.FriendChallengeCreateRequest(
        challenge_type="DIRECT",
        total_rounds=5,
    )
    assert captured["kwargs"] == {
        "creator_user_id": 101,
        "created_after_utc": NOW_UTC,
    }


@pytest.mark.asyncio
async def test_resolve_create_request_returns_open_request_after_open_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_create_limits,
        "resolve_duel_rounds",
        lambda **_: 7,
    )
    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_live_for_user",
        _async_return(0),
    )
    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_live_open_by_creator",
        _async_return(0),
    )
    monkeypatch.setattr(
        friend_challenges_create_limits,
        "berlin_day_start_utc",
        lambda **_: NOW_UTC,
    )
    monkeypatch.setattr(
        friend_challenges_create_limits.FriendChallengesRepo,
        "count_created_since",
        _async_return(0),
    )

    request = await friend_challenges_create_limits.resolve_friend_challenge_create_request(
        _Session(),
        creator_user_id=101,
        challenge_type="OPEN",
        total_rounds=12,
        now_utc=NOW_UTC,
    )

    assert request == friend_challenges_create_limits.FriendChallengeCreateRequest(
        challenge_type="OPEN",
        total_rounds=7,
    )
