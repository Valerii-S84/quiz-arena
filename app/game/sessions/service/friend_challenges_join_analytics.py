from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge


async def emit_friend_challenge_joined_events(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    happened_at: datetime,
    source: str,
    user_id: int,
) -> None:
    await emit_analytics_event(
        session,
        event_type="friend_challenge_joined",
        source=source,
        happened_at=happened_at,
        user_id=user_id,
        payload={
            "challenge_id": str(challenge.id),
            "creator_user_id": challenge.creator_user_id,
            "mode_code": challenge.mode_code,
            "total_rounds": challenge.total_rounds,
            "expires_at": challenge.expires_at.isoformat(),
            "series_id": str(challenge.series_id) if challenge.series_id is not None else None,
            "series_game_number": challenge.series_game_number,
            "series_best_of": challenge.series_best_of,
        },
    )
    await emit_analytics_event(
        session,
        event_type="duel_accepted",
        source=source,
        happened_at=happened_at,
        user_id=user_id,
        payload={
            "challenge_id": str(challenge.id),
            "challenge_type": challenge.challenge_type,
            "format": challenge.total_rounds,
        },
    )
