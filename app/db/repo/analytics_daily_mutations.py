from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_daily import AnalyticsDaily
from app.db.repo.analytics_models import AnalyticsDailyUpsert


async def upsert_daily(session: AsyncSession, *, row: AnalyticsDailyUpsert) -> None:
    values = asdict(row)
    stmt = insert(AnalyticsDaily).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AnalyticsDaily.local_date_berlin],
        set_=values,
    )
    await session.execute(stmt)
