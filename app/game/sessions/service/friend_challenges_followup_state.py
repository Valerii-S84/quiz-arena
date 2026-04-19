from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge

from .friend_challenges_followup_challenge_state import load_followup_friend_challenge
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
    challenge = await load_followup_friend_challenge(
        session,
        challenge_id=challenge_id,
        initiator_user_id=initiator_user_id,
        now_utc=now_utc,
    )
    return FriendChallengeFollowupContext(
        challenge=challenge,
        opponent_user_id=_resolve_challenge_opponent_user_id(
            challenge=challenge,
            initiator_user_id=initiator_user_id,
        ),
    )
