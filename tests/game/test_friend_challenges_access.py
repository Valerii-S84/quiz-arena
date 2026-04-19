from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengePaymentRequiredError
from app.game.sessions.service import friend_challenges_access, friend_challenges_access_state
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_resolve_friend_challenge_access_type_propagates_state_loading_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_access_error(*args, **kwargs):
        del args, kwargs
        raise FriendChallengeAccessError

    monkeypatch.setattr(
        friend_challenges_access,
        "load_friend_challenge_access_state",
        _raise_access_error,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_access._resolve_friend_challenge_access_type(
            _Session(),
            creator_user_id=101,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "expected_access_type"),
    [
        (
            friend_challenges_access_state.FriendChallengeAccessState(premium_active=True),
            "PREMIUM",
        ),
        (
            friend_challenges_access_state.FriendChallengeAccessState(
                premium_active=False,
                free_count=1,
            ),
            "FREE",
        ),
        (
            friend_challenges_access_state.FriendChallengeAccessState(
                premium_active=False,
                free_count=2,
                paid_count=0,
                paid_tickets=1,
            ),
            "PAID_TICKET",
        ),
    ],
    ids=["premium", "free_quota", "paid_ticket"],
)
async def test_resolve_friend_challenge_access_type_returns_expected_access_type(
    monkeypatch: pytest.MonkeyPatch,
    state: friend_challenges_access_state.FriendChallengeAccessState,
    expected_access_type: str,
) -> None:
    monkeypatch.setattr(friend_challenges_access, "FRIEND_CHALLENGE_FREE_CREATES", 2)

    async def _fake_load_state(*_args, **_kwargs):
        return state

    monkeypatch.setattr(
        friend_challenges_access,
        "load_friend_challenge_access_state",
        _fake_load_state,
    )

    access_type = await friend_challenges_access._resolve_friend_challenge_access_type(
        _Session(),
        creator_user_id=101,
        now_utc=NOW_UTC,
    )

    assert access_type == expected_access_type


@pytest.mark.asyncio
async def test_resolve_friend_challenge_access_type_raises_when_paid_tickets_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(friend_challenges_access, "FRIEND_CHALLENGE_FREE_CREATES", 2)

    async def _fake_load_state(*_args, **_kwargs):
        return friend_challenges_access_state.FriendChallengeAccessState(
            premium_active=False,
            free_count=2,
            paid_count=1,
            paid_tickets=1,
        )

    monkeypatch.setattr(
        friend_challenges_access,
        "load_friend_challenge_access_state",
        _fake_load_state,
    )

    with pytest.raises(FriendChallengePaymentRequiredError):
        await friend_challenges_access._resolve_friend_challenge_access_type(
            _Session(),
            creator_user_id=101,
            now_utc=NOW_UTC,
        )
