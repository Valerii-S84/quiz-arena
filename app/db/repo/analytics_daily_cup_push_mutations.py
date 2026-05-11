from __future__ import annotations

from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.analytics_constants import DAILY_CUP_UNIQUE_PUSH_EVENT_TYPES_SQL
from app.db.models.analytics_events import AnalyticsEvent


async def create_daily_cup_push_event_once(
    session: AsyncSession,
    *,
    event_type: str,
    source: str,
    user_id: int,
    local_date_berlin: date,
    payload: dict[str, object],
    happened_at: datetime,
) -> bool:
    stmt = (
        insert(AnalyticsEvent)
        .values(
            event_type=event_type,
            source=source,
            user_id=user_id,
            local_date_berlin=local_date_berlin,
            payload=payload,
            happened_at=happened_at,
        )
        .on_conflict_do_nothing(
            index_elements=[
                AnalyticsEvent.event_type,
                AnalyticsEvent.user_id,
                sa.text("(payload ->> 'tournament_id')"),
            ],
            index_where=sa.text(
                "user_id IS NOT NULL "
                "AND payload ? 'tournament_id' "
                "AND event_type IN "
                f"({DAILY_CUP_UNIQUE_PUSH_EVENT_TYPES_SQL})"
            ),
        )
        .returning(AnalyticsEvent.id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
