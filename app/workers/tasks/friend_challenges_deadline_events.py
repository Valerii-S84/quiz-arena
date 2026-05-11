from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_WORKER
from app.workers.tasks.friend_challenges_deadline_types import DeadlinePayload

AnalyticsEmitter = Callable[..., Awaitable[None]]


async def emit_duel_expired_event(
    session: AsyncSession,
    *,
    item: DeadlinePayload,
    happened_at: datetime,
    emit_event: AnalyticsEmitter,
) -> None:
    await emit_event(
        session,
        event_type="duel_expired",
        source=EVENT_SOURCE_WORKER,
        happened_at=happened_at,
        user_id=None,
        payload=_build_expired_analytics_payload(item),
    )


async def emit_notification_event(
    session: AsyncSession,
    *,
    event_type: str,
    payload: DeadlinePayload,
    happened_at: datetime,
    emit_event: AnalyticsEmitter,
) -> None:
    await emit_event(
        session,
        event_type=event_type,
        source=EVENT_SOURCE_WORKER,
        happened_at=happened_at,
        user_id=None,
        payload=payload,
    )


def _build_expired_analytics_payload(item: DeadlinePayload) -> DeadlinePayload:
    expires_at = item["expires_at"]
    if not isinstance(expires_at, datetime):
        raise TypeError("expires_at must be datetime")
    return {
        "challenge_id": item["challenge_id"],
        "creator_user_id": item["creator_user_id"],
        "opponent_user_id": item["opponent_user_id"],
        "creator_score": item["creator_score"],
        "opponent_score": item["opponent_score"],
        "winner_user_id": item["winner_user_id"],
        "status": item["status"],
        "previous_status": item["previous_status"],
        "total_rounds": item["total_rounds"],
        "expires_at": expires_at.isoformat(),
    }
