from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.game.sessions.errors import FriendChallengeAccessError
from app.game.sessions.service import friend_challenges_access_state
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
async def test_load_friend_challenge_access_state_raises_when_creator_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_access_state.UsersRepo,
        "get_by_id_for_update",
        _async_return(None),
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_access_state.load_friend_challenge_access_state(
            _Session(),
            creator_user_id=101,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_load_friend_challenge_access_state_returns_premium_without_counting_quotas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        friend_challenges_access_state.UsersRepo,
        "get_by_id_for_update",
        _async_return(object()),
    )
    monkeypatch.setattr(
        friend_challenges_access_state.EntitlementsRepo,
        "has_active_premium",
        _async_return(True),
    )

    async def _unexpected_count(*args, **kwargs):
        del args, kwargs
        raise AssertionError("quota counters should not run for premium creator")

    monkeypatch.setattr(
        friend_challenges_access_state.FriendChallengesRepo,
        "count_by_creator_access_type",
        _unexpected_count,
    )

    state = await friend_challenges_access_state.load_friend_challenge_access_state(
        _Session(),
        creator_user_id=101,
        now_utc=NOW_UTC,
    )

    assert state == friend_challenges_access_state.FriendChallengeAccessState(
        premium_active=True,
    )


@pytest.mark.asyncio
async def test_load_friend_challenge_access_state_returns_free_quota_counts_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    count_calls: list[dict[str, object]] = []

    async def _fake_count_by_creator_access_type(session, **kwargs):
        del session
        count_calls.append(kwargs)
        return 1

    monkeypatch.setattr(friend_challenges_access_state, "FRIEND_CHALLENGE_FREE_CREATES", 2)
    monkeypatch.setattr(
        friend_challenges_access_state.UsersRepo,
        "get_by_id_for_update",
        _async_return(object()),
    )
    monkeypatch.setattr(
        friend_challenges_access_state.EntitlementsRepo,
        "has_active_premium",
        _async_return(False),
    )
    monkeypatch.setattr(
        friend_challenges_access_state.FriendChallengesRepo,
        "count_by_creator_access_type",
        _fake_count_by_creator_access_type,
    )

    async def _unexpected_paid_tickets(*args, **kwargs):
        del args, kwargs
        raise AssertionError("paid ticket lookup should not run before free quota is exhausted")

    monkeypatch.setattr(
        friend_challenges_access_state.PurchasesRepo,
        "count_credited_product",
        _unexpected_paid_tickets,
    )

    state = await friend_challenges_access_state.load_friend_challenge_access_state(
        _Session(),
        creator_user_id=101,
        now_utc=NOW_UTC,
    )

    assert state == friend_challenges_access_state.FriendChallengeAccessState(
        premium_active=False,
        free_count=1,
    )
    assert count_calls == [
        {
            "creator_user_id": 101,
            "access_type": "FREE",
            "since": NOW_UTC.replace(hour=0, minute=0, second=0, microsecond=0),
        }
    ]


@pytest.mark.asyncio
async def test_load_friend_challenge_access_state_loads_paid_ticket_counts_after_free_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    count_calls: list[dict[str, object]] = []
    count_results = iter([2, 1])

    async def _fake_count_by_creator_access_type(session, **kwargs):
        del session
        count_calls.append(kwargs)
        return next(count_results)

    monkeypatch.setattr(friend_challenges_access_state, "FRIEND_CHALLENGE_FREE_CREATES", 2)
    monkeypatch.setattr(
        friend_challenges_access_state.UsersRepo,
        "get_by_id_for_update",
        _async_return(object()),
    )
    monkeypatch.setattr(
        friend_challenges_access_state.EntitlementsRepo,
        "has_active_premium",
        _async_return(False),
    )
    monkeypatch.setattr(
        friend_challenges_access_state.FriendChallengesRepo,
        "count_by_creator_access_type",
        _fake_count_by_creator_access_type,
    )
    monkeypatch.setattr(
        friend_challenges_access_state.PurchasesRepo,
        "count_credited_product",
        _async_return(3),
    )

    state = await friend_challenges_access_state.load_friend_challenge_access_state(
        _Session(),
        creator_user_id=101,
        now_utc=NOW_UTC,
    )

    assert state == friend_challenges_access_state.FriendChallengeAccessState(
        premium_active=False,
        free_count=2,
        paid_count=1,
        paid_tickets=3,
    )
    assert count_calls == [
        {
            "creator_user_id": 101,
            "access_type": "FREE",
            "since": NOW_UTC.replace(hour=0, minute=0, second=0, microsecond=0),
        },
        {
            "creator_user_id": 101,
            "access_type": "PAID_TICKET",
        },
    ]
