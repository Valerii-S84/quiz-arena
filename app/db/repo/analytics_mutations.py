from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_daily import AnalyticsDaily
from app.db.models.analytics_events import AnalyticsEvent
from app.db.repo.analytics_models import AnalyticsDailyUpsert


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


async def upsert_daily(session: AsyncSession, *, row: AnalyticsDailyUpsert) -> None:
    values = asdict(row)
    stmt = insert(AnalyticsDaily).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AnalyticsDaily.local_date_berlin],
        set_=values,
    )
    await session.execute(stmt)


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
