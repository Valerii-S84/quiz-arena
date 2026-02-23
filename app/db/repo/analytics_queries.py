from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_daily import AnalyticsDaily


async def list_daily(
    session: AsyncSession,
    *,
    limit: int,
) -> list[AnalyticsDaily]:
    stmt = select(AnalyticsDaily).order_by(AnalyticsDaily.local_date_berlin.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
