from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge


def _series_id_value(*, duel: FriendChallenge) -> str | None:
    if duel.series_id is None:
        return None
    return str(duel.series_id)


def _friend_challenge_created_payload(
    *,
    duel: FriendChallenge,
    source_challenge_id: UUID,
    entrypoint: str,
) -> dict[str, object]:
    return {
        "challenge_id": str(duel.id),
        "mode_code": duel.mode_code,
        "access_type": duel.access_type,
        "total_rounds": duel.total_rounds,
        "entrypoint": entrypoint,
        "source_challenge_id": str(source_challenge_id),
        "series_id": _series_id_value(duel=duel),
        "series_game_number": duel.series_game_number,
        "series_best_of": duel.series_best_of,
        "expires_at": duel.expires_at.isoformat(),
    }


def _series_progress_payload(
    *,
    duel: FriendChallenge,
    source_challenge_id: UUID,
    opponent_user_id: int | None,
) -> dict[str, object]:
    return {
        "challenge_id": str(duel.id),
        "source_challenge_id": str(source_challenge_id),
        "opponent_user_id": opponent_user_id,
        "series_id": _series_id_value(duel=duel),
        "series_game_number": duel.series_game_number,
        "series_best_of": duel.series_best_of,
    }


async def _emit_series_duel_created_event_pair(
    session: AsyncSession,
    *,
    duel: FriendChallenge,
    source_challenge_id: UUID,
    opponent_user_id: int | None,
    happened_at: datetime,
    source: str,
    initiator_user_id: int,
    entrypoint: str,
    series_event_type: str,
) -> None:
    await emit_analytics_event(
        session,
        event_type="friend_challenge_created",
        source=source,
        happened_at=happened_at,
        user_id=initiator_user_id,
        payload=_friend_challenge_created_payload(
            duel=duel,
            source_challenge_id=source_challenge_id,
            entrypoint=entrypoint,
        ),
    )
    await emit_analytics_event(
        session,
        event_type=series_event_type,
        source=source,
        happened_at=happened_at,
        user_id=initiator_user_id,
        payload=_series_progress_payload(
            duel=duel,
            source_challenge_id=source_challenge_id,
            opponent_user_id=opponent_user_id,
        ),
    )


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
    await _emit_series_duel_created_event_pair(
        session,
        duel=duel,
        source_challenge_id=source_challenge_id,
        opponent_user_id=opponent_user_id,
        happened_at=happened_at,
        source=source,
        initiator_user_id=initiator_user_id,
        entrypoint="best_of_series",
        series_event_type="friend_challenge_series_started",
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
    await _emit_series_duel_created_event_pair(
        session,
        duel=duel,
        source_challenge_id=source_challenge_id,
        opponent_user_id=opponent_user_id,
        happened_at=happened_at,
        source=source,
        initiator_user_id=initiator_user_id,
        entrypoint="best_of_series_next_game",
        series_event_type="friend_challenge_series_game_created",
    )
