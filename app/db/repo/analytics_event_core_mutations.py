from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_events import AnalyticsEvent


async def create_event(
    session: AsyncSession,
    *,
    event_type: str,
    source: str,
    user_id: int | None,
    local_date_berlin: date,
    payload: dict[str, object],
    happened_at: datetime,
) -> AnalyticsEvent:
    event = AnalyticsEvent(
        event_type=event_type,
        source=source,
        user_id=user_id,
        local_date_berlin=local_date_berlin,
        payload=payload,
        happened_at=happened_at,
    )
    session.add(event)
    await session.flush()
    return event
