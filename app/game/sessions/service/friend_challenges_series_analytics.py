from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge


async def emit_series_started_duel_created_events(
    session: AsyncSession,
    *,
    duel: FriendChallenge,
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
            "challenge_id": str(duel.id),
            "mode_code": duel.mode_code,
            "access_type": duel.access_type,
            "total_rounds": duel.total_rounds,
            "entrypoint": "best_of_series",
            "source_challenge_id": str(source_challenge_id),
            "series_id": str(duel.series_id) if duel.series_id is not None else None,
            "series_game_number": duel.series_game_number,
            "series_best_of": duel.series_best_of,
            "expires_at": duel.expires_at.isoformat(),
        },
    )
    await emit_analytics_event(
        session,
        event_type="friend_challenge_series_started",
        source=source,
        happened_at=happened_at,
        user_id=initiator_user_id,
        payload={
            "challenge_id": str(duel.id),
            "source_challenge_id": str(source_challenge_id),
            "opponent_user_id": opponent_user_id,
            "series_id": str(duel.series_id) if duel.series_id is not None else None,
            "series_game_number": duel.series_game_number,
            "series_best_of": duel.series_best_of,
        },
    )


async def emit_series_next_game_created_events(
    session: AsyncSession,
    *,
    duel: FriendChallenge,
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
            "challenge_id": str(duel.id),
            "mode_code": duel.mode_code,
            "access_type": duel.access_type,
            "total_rounds": duel.total_rounds,
            "entrypoint": "best_of_series_next_game",
            "source_challenge_id": str(source_challenge_id),
            "series_id": str(duel.series_id) if duel.series_id is not None else None,
            "series_game_number": duel.series_game_number,
            "series_best_of": duel.series_best_of,
            "expires_at": duel.expires_at.isoformat(),
        },
    )
    await emit_analytics_event(
        session,
        event_type="friend_challenge_series_game_created",
        source=source,
        happened_at=happened_at,
        user_id=initiator_user_id,
        payload={
            "challenge_id": str(duel.id),
            "source_challenge_id": str(source_challenge_id),
            "opponent_user_id": opponent_user_id,
            "series_id": str(duel.series_id) if duel.series_id is not None else None,
            "series_game_number": duel.series_game_number,
            "series_best_of": duel.series_best_of,
        },
    )
