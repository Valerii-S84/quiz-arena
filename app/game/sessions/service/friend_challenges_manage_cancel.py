from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.game.friend_challenges.constants import DUEL_STATUS_CANCELED
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_manage_state import load_manageable_friend_challenge
from .friend_challenges_records import _build_friend_challenge_snapshot


async def cancel_friend_challenge_by_creator(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    challenge = await load_manageable_friend_challenge(
        session,
        challenge_id=challenge_id,
        user_id=user_id,
        now_utc=now_utc,
    )
    challenge.status = DUEL_STATUS_CANCELED
    challenge.completed_at = now_utc
    challenge.updated_at = now_utc
    await emit_analytics_event(
        session,
        event_type="duel_canceled_by_creator",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload={
            "challenge_id": str(challenge.id),
            "format": int(challenge.total_rounds),
        },
    )
    return _build_friend_challenge_snapshot(challenge)
