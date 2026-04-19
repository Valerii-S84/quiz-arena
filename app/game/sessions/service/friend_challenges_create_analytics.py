from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge

from .friend_challenges_create_standard_analytics import (
    emit_standard_duel_created_events as emit_standard_duel_created_events_impl,
)


async def emit_standard_duel_created_events(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    happened_at: datetime,
    source: str,
    creator_user_id: int,
) -> None:
    await emit_standard_duel_created_events_impl(
        session,
        challenge=challenge,
        happened_at=happened_at,
        source=source,
        creator_user_id=creator_user_id,
    )


async def emit_rematch_duel_created_events(
    session: AsyncSession,
    *,
    rematch: FriendChallenge,
    source_challenge_id: UUID,
    opponent_user_id: int | None,
    happened_at: datetime,
    source: str,
    initiator_user_id: int,
) -> None:
    await emit_analytics_event(
        session,
        event_type="friend_challenge_created",
        source=source,
        happened_at=happened_at,
        user_id=initiator_user_id,
        payload={
            "challenge_id": str(rematch.id),
            "mode_code": rematch.mode_code,
            "challenge_type": rematch.challenge_type,
            "access_type": rematch.access_type,
            "total_rounds": rematch.total_rounds,
            "entrypoint": "rematch",
            "source_challenge_id": str(source_challenge_id),
            "expires_at": rematch.expires_at.isoformat(),
            "series_id": (str(rematch.series_id) if rematch.series_id is not None else None),
            "series_game_number": rematch.series_game_number,
            "series_best_of": rematch.series_best_of,
        },
    )
    await emit_analytics_event(
        session,
        event_type="duel_revanche_created",
        source=source,
        happened_at=happened_at,
        user_id=initiator_user_id,
        payload={
            "challenge_id": str(rematch.id),
            "source_challenge_id": str(source_challenge_id),
            "opponent_user_id": opponent_user_id,
            "format": rematch.total_rounds,
            "total_rounds": rematch.total_rounds,
            "expires_at": rematch.expires_at.isoformat(),
            "series_id": (str(rematch.series_id) if rematch.series_id is not None else None),
            "series_game_number": rematch.series_game_number,
            "series_best_of": rematch.series_best_of,
        },
    )
