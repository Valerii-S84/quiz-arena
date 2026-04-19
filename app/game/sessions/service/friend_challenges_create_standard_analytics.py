from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge


async def emit_standard_duel_created_events(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    happened_at: datetime,
    source: str,
    creator_user_id: int,
) -> None:
    await emit_analytics_event(
        session,
        event_type="friend_challenge_created",
        source=source,
        happened_at=happened_at,
        user_id=creator_user_id,
        payload={
            "challenge_id": str(challenge.id),
            "mode_code": challenge.mode_code,
            "challenge_type": challenge.challenge_type,
            "access_type": challenge.access_type,
            "total_rounds": challenge.total_rounds,
            "entrypoint": "standard",
            "expires_at": challenge.expires_at.isoformat(),
            "series_id": None,
            "series_game_number": challenge.series_game_number,
            "series_best_of": challenge.series_best_of,
        },
    )
    await emit_analytics_event(
        session,
        event_type="duel_created",
        source=source,
        happened_at=happened_at,
        user_id=creator_user_id,
        payload={
            "challenge_id": str(challenge.id),
            "type": challenge.challenge_type,
            "format": challenge.total_rounds,
        },
    )
