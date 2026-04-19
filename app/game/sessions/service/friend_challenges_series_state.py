from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from . import friend_challenges_followup_state

_FriendChallengeSeriesContext = friend_challenges_followup_state.FriendChallengeFollowupContext


async def load_friend_challenge_series_context(
    session: AsyncSession,
    *,
    challenge_id: UUID,
    initiator_user_id: int,
    now_utc: datetime,
) -> _FriendChallengeSeriesContext:
    return await friend_challenges_followup_state.load_friend_challenge_followup_context(
        session,
        challenge_id=challenge_id,
        initiator_user_id=initiator_user_id,
        now_utc=now_utc,
    )
