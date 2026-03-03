from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_daily import AnalyticsDaily
from app.db.models.analytics_events import AnalyticsEvent


async def list_daily(
    session: AsyncSession,
    *,
    limit: int,
) -> list[AnalyticsDaily]:
    stmt = select(AnalyticsDaily).order_by(AnalyticsDaily.local_date_berlin.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_user_ids_by_event_type_and_tournament(
    session: AsyncSession,
    *,
    event_type: str,
    tournament_id: str,
    user_ids: list[int],
) -> set[int]:
    if not user_ids:
        return set()
    stmt = select(AnalyticsEvent.user_id).where(
        AnalyticsEvent.event_type == event_type,
        AnalyticsEvent.user_id.is_not(None),
        AnalyticsEvent.user_id.in_(tuple(user_ids)),
        AnalyticsEvent.payload["tournament_id"].astext == tournament_id,
    )
    result = await session.execute(stmt)
    return {int(user_id) for user_id in result.scalars().all() if user_id is not None}
