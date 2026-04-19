from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError

from .friend_challenges_expiry import (
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)


async def load_followup_friend_challenge(
    session: AsyncSession,
    *,
    challenge_id: UUID,
    initiator_user_id: int,
    now_utc: datetime,
) -> FriendChallenge:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError
    if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
        )
    if challenge.status not in {"COMPLETED", "EXPIRED", "WALKOVER"}:
        raise FriendChallengeAccessError
    if initiator_user_id not in {challenge.creator_user_id, challenge.opponent_user_id}:
        raise FriendChallengeAccessError
    return challenge
