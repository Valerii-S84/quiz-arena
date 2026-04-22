from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge

from .friend_challenges_analytics import (
    emit_rematch_duel_created_events as emit_rematch_duel_created_events_impl,
)
from .friend_challenges_analytics import (
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
    await emit_rematch_duel_created_events_impl(
        session,
        rematch=rematch,
        source_challenge_id=source_challenge_id,
        opponent_user_id=opponent_user_id,
        happened_at=happened_at,
        source=source,
        initiator_user_id=initiator_user_id,
    )
