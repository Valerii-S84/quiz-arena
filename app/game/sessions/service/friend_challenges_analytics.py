from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge


async def _emit_friend_challenge_expired_event(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    happened_at: datetime,
    source: str,
) -> None:
    await emit_analytics_event(
        session,
        event_type="duel_expired",
        source=source,
        happened_at=happened_at,
        user_id=None,
        payload={
            "challenge_id": str(challenge.id),
            "creator_user_id": challenge.creator_user_id,
            "opponent_user_id": challenge.opponent_user_id,
            "creator_score": challenge.creator_score,
            "opponent_score": challenge.opponent_score,
            "total_rounds": challenge.total_rounds,
            "expires_at": challenge.expires_at.isoformat(),
        },
    )
