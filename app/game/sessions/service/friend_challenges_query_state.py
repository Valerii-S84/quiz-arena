from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import normalize_duel_status
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError

from .friend_challenges_expiry import (
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)


async def load_friend_challenge_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallenge:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError
    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=challenge.opponent_user_id is not None,
    )
    if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
        )
    if user_id not in {challenge.creator_user_id, challenge.opponent_user_id}:
        raise FriendChallengeAccessError
    return challenge
