from __future__ import annotations

import pytest

from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.friend_challenges.constants import DUEL_TYPE_DIRECT, DUEL_TYPE_OPEN
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeLimitExceededError
from app.game.sessions.service import friend_challenges_create
from tests.game.friend_challenges_unit_support import (
    FIXED_CHALLENGE_ID,
    NOW_UTC,
    Session,
    async_return,
    duel,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("challenge_type", [DUEL_TYPE_DIRECT, DUEL_TYPE_OPEN])
async def test_create_friend_challenge_success(
    monkeypatch: pytest.MonkeyPatch,
    challenge_type: str,
) -> None:
    created = duel(id=FIXED_CHALLENGE_ID, challenge_type=challenge_type)
    create_calls: list[dict[str, object]] = []

    async def _fake_create_row(_session, **kwargs):
        create_calls.append(kwargs)
        created.question_ids = kwargs["question_ids"]
        return created

    _patch_create_dependencies(monkeypatch)
    monkeypatch.setattr(friend_challenges_create, "uuid4", lambda: FIXED_CHALLENGE_ID)
    monkeypatch.setattr(friend_challenges_create, "_create_friend_challenge_row", _fake_create_row)
    monkeypatch.setattr(
        friend_challenges_create,
        "emit_standard_duel_created_events",
        async_return(None),
    )

    result = await friend_challenges_create.create_friend_challenge(
        Session(),
        creator_user_id=11,
        mode_code="QUICK_MIX_A1A2",
        now_utc=NOW_UTC,
        challenge_type=challenge_type,
        total_rounds=DUEL_QUESTION_COUNT,
    )

    assert result.challenge_id == FIXED_CHALLENGE_ID
    assert result.question_ids == ("q-1", "q-2", "q-3", "q-4", "q-5", "q-6", "q-7")
    assert create_calls[0]["challenge_type"] == challenge_type
    assert create_calls[0]["access_type"] == "FREE"


@pytest.mark.asyncio
async def test_create_rejects_invalid_type_before_limit_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_limit_query(*_args, **_kwargs):
        pytest.fail("invalid challenge types should fail before limit queries")

    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "count_live_for_user",
        _unexpected_limit_query,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_create.create_friend_challenge(
            Session(),
            creator_user_id=11,
            mode_code="QUICK_MIX_A1A2",
            now_utc=NOW_UTC,
            challenge_type="INVALID",
            total_rounds=DUEL_QUESTION_COUNT,
        )


@pytest.mark.asyncio
async def test_create_rejects_live_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "count_live_for_user",
        async_return(friend_challenges_create.DUEL_MAX_ACTIVE_PER_USER),
    )

    with pytest.raises(FriendChallengeLimitExceededError):
        await friend_challenges_create.create_friend_challenge(
            Session(),
            creator_user_id=11,
            mode_code="QUICK_MIX_A1A2",
            now_utc=NOW_UTC,
            total_rounds=DUEL_QUESTION_COUNT,
        )


@pytest.mark.asyncio
async def test_create_rejects_duplicate_open_duel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "count_live_for_user",
        async_return(0),
    )
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "count_live_open_by_creator",
        async_return(1),
    )

    with pytest.raises(FriendChallengeLimitExceededError):
        await friend_challenges_create.create_friend_challenge(
            Session(),
            creator_user_id=11,
            mode_code="QUICK_MIX_A1A2",
            now_utc=NOW_UTC,
            challenge_type=DUEL_TYPE_OPEN,
            total_rounds=DUEL_QUESTION_COUNT,
        )


@pytest.mark.asyncio
async def test_create_rejects_daily_create_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "count_live_for_user",
        async_return(0),
    )
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "count_created_since",
        async_return(friend_challenges_create.DUEL_MAX_NEW_PER_DAY),
    )

    with pytest.raises(FriendChallengeLimitExceededError):
        await friend_challenges_create.create_friend_challenge(
            Session(),
            creator_user_id=11,
            mode_code="QUICK_MIX_A1A2",
            now_utc=NOW_UTC,
            total_rounds=DUEL_QUESTION_COUNT,
        )


def _patch_create_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "count_live_for_user",
        async_return(0),
    )
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "count_live_open_by_creator",
        async_return(0),
    )
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "count_created_since",
        async_return(0),
    )
    monkeypatch.setattr(
        friend_challenges_create,
        "_resolve_friend_challenge_access_type",
        async_return("FREE"),
    )
    monkeypatch.setattr(
        friend_challenges_create,
        "select_duel_question_ids",
        async_return(["q-1", "q-2", "q-3", "q-4", "q-5", "q-6", "q-7"]),
    )
