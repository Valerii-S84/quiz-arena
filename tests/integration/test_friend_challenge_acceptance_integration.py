from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.session import SessionLocal
from app.game.friend_challenges.constants import DUEL_TYPE_OPEN
from app.game.sessions.errors import (
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
)
from app.game.sessions.service import GameSessionService
from tests.integration.friend_challenge_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_open_challenge_concurrent_accept_allows_only_one_opponent() -> None:
    now_utc = datetime(2026, 2, 20, 10, 0, tzinfo=UTC)
    creator_user_id = await _create_user("fc_race_creator")
    first_user_id = await _create_user("fc_race_first")
    second_user_id = await _create_user("fc_race_second")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            challenge_type=DUEL_TYPE_OPEN,
            total_rounds=5,
        )

    async def _join(user_id: int):
        async with SessionLocal.begin() as session:
            return await GameSessionService.join_friend_challenge_by_id(
                session,
                user_id=user_id,
                challenge_id=challenge.challenge_id,
                now_utc=now_utc + timedelta(seconds=1),
            )

    first_result, second_result = await asyncio.gather(
        _join(first_user_id),
        _join(second_user_id),
        return_exceptions=True,
    )

    outcomes = [first_result, second_result]
    joined_success = [item for item in outcomes if not isinstance(item, Exception)]
    join_errors = [item for item in outcomes if isinstance(item, Exception)]

    assert len(joined_success) == 1
    assert len(join_errors) == 1
    assert isinstance(join_errors[0], FriendChallengeFullError)
    assert joined_success[0].joined_now is True

    async with SessionLocal.begin() as session:
        row = await FriendChallengesRepo.get_by_id_for_update(session, challenge.challenge_id)
        assert row is not None
        assert row.status == "ACCEPTED"
        assert row.opponent_user_id in {first_user_id, second_user_id}


@pytest.mark.asyncio
async def test_join_after_expired_returns_expired_error() -> None:
    now_utc = datetime(2026, 2, 20, 11, 0, tzinfo=UTC)
    creator_user_id = await _create_user("fc_expired_accept_creator")
    joiner_user_id = await _create_user("fc_expired_accept_joiner")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            challenge_type=DUEL_TYPE_OPEN,
            total_rounds=5,
        )
        row = await FriendChallengesRepo.get_by_id_for_update(session, challenge.challenge_id)
        assert row is not None
        row.expires_at = now_utc - timedelta(seconds=1)

    async with SessionLocal.begin() as session:
        with pytest.raises(FriendChallengeExpiredError):
            await GameSessionService.join_friend_challenge_by_id(
                session,
                user_id=joiner_user_id,
                challenge_id=challenge.challenge_id,
                now_utc=now_utc,
            )


@pytest.mark.asyncio
async def test_join_after_completed_returns_completed_error() -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    creator_user_id = await _create_user("fc_completed_accept_creator")
    first_joiner_user_id = await _create_user("fc_completed_accept_first")
    second_joiner_user_id = await _create_user("fc_completed_accept_second")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            challenge_type=DUEL_TYPE_OPEN,
            total_rounds=5,
        )
        await GameSessionService.join_friend_challenge_by_id(
            session,
            user_id=first_joiner_user_id,
            challenge_id=challenge.challenge_id,
            now_utc=now_utc,
        )
        row = await FriendChallengesRepo.get_by_id_for_update(session, challenge.challenge_id)
        assert row is not None
        row.status = "COMPLETED"
        row.completed_at = now_utc

    async with SessionLocal.begin() as session:
        with pytest.raises(FriendChallengeCompletedError):
            await GameSessionService.join_friend_challenge_by_id(
                session,
                user_id=second_joiner_user_id,
                challenge_id=challenge.challenge_id,
                now_utc=now_utc + timedelta(seconds=1),
            )
