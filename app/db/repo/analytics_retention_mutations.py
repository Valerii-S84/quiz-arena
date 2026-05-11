from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_events import AnalyticsEvent


async def delete_events_created_before(
    session: AsyncSession,
    *,
    cutoff_utc: datetime,
    limit: int,
) -> int:
    resolved_limit = max(1, int(limit))
    candidate_ids = (
        select(AnalyticsEvent.id)
        .where(AnalyticsEvent.created_at < cutoff_utc)
        .order_by(AnalyticsEvent.created_at.asc(), AnalyticsEvent.id.asc())
        .limit(resolved_limit)
        .scalar_subquery()
    )
    stmt = (
        delete(AnalyticsEvent)
        .where(AnalyticsEvent.id.in_(candidate_ids))
        .returning(AnalyticsEvent.id)
    )
    result = await session.execute(stmt)
    return len(list(result.scalars()))
