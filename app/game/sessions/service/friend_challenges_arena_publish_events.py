from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.models.friend_challenges import FriendChallenge

ExpireFriendChallenge = Callable[..., bool]
EmitExpiredEvent = Callable[..., Awaitable[None]]


async def expire_friend_challenge_for_arena_publish(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    now_utc: datetime,
    expire_friend_challenge_if_due: ExpireFriendChallenge,
    emit_friend_challenge_expired_event: EmitExpiredEvent,
) -> None:
    if not expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        return
    await emit_friend_challenge_expired_event(
        session,
        challenge=challenge,
        happened_at=now_utc,
        source=EVENT_SOURCE_BOT,
    )
