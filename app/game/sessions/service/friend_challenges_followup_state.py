from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError

from .friend_challenges_internal import (
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)
from .friend_challenges_series_utils import _resolve_challenge_opponent_user_id


@dataclass(slots=True)
class FriendChallengeFollowupContext:
    challenge: FriendChallenge
    opponent_user_id: int


async def load_friend_challenge_followup_context(
    session: AsyncSession,
    *,
    challenge_id: UUID,
    initiator_user_id: int,
    now_utc: datetime,
) -> FriendChallengeFollowupContext:
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
    return FriendChallengeFollowupContext(
        challenge=challenge,
        opponent_user_id=_resolve_challenge_opponent_user_id(
            challenge=challenge,
            initiator_user_id=initiator_user_id,
        ),
    )
