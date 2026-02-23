from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.session import SessionLocal
from app.game.sessions.errors import FriendChallengeExpiredError
from app.game.sessions.service import GameSessionService
from tests.integration.friend_challenge_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_friend_challenge_start_round_fails_when_expired() -> None:
    now_utc = datetime(2026, 2, 19, 18, 40, tzinfo=UTC)
    creator_user_id = await _create_user("fc_expired_creator")

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=3,
        )
        row = await FriendChallengesRepo.get_by_id_for_update(session, challenge.challenge_id)
        assert row is not None
        row.expires_at = now_utc - timedelta(minutes=1)

        with pytest.raises(FriendChallengeExpiredError):
            await GameSessionService.start_friend_challenge_round(
                session,
                user_id=creator_user_id,
                challenge_id=challenge.challenge_id,
                idempotency_key="fc:expired:start",
                now_utc=now_utc,
            )
