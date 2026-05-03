from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.analytics_repo import AnalyticsRepo
from app.game.arena_duels.constants import ARENA_REVANCHE_SENT_EVENT
from app.game.arena_duels.revanche_friend_challenge import build_arena_revanche_payload
from app.game.arena_duels.revanche_types import ArenaRevancheRequest


async def lock_arena_revanche_delivery(
    session: AsyncSession,
    *,
    request: ArenaRevancheRequest,
) -> None:
    await AnalyticsRepo.lock_arena_revanche_event_key(
        session,
        event_type=ARENA_REVANCHE_SENT_EVENT,
        user_id=request.context.sender_user_id,
        payload=build_arena_revanche_payload(context=request.context),
    )


async def is_arena_revanche_sent(
    session: AsyncSession,
    *,
    request: ArenaRevancheRequest,
) -> bool:
    return await AnalyticsRepo.has_arena_revanche_event(
        session,
        event_type=ARENA_REVANCHE_SENT_EVENT,
        user_id=request.context.sender_user_id,
        payload=build_arena_revanche_payload(context=request.context),
    )
