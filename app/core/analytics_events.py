from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.analytics_repo import AnalyticsRepo
from app.economy.energy.constants import BERLIN_TIMEZONE

EVENT_SOURCE_BOT = "BOT"
EVENT_SOURCE_WORKER = "WORKER"
EVENT_SOURCE_API = "API"
EVENT_SOURCE_SYSTEM = "SYSTEM"


async def emit_analytics_event(
    session: AsyncSession,
    *,
    event_type: str,
    source: str,
    happened_at: datetime,
    user_id: int | None = None,
    payload: dict[str, object] | None = None,
) -> None:
    local_date_berlin = happened_at.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()
    await AnalyticsRepo.create_event(
        session,
        event_type=event_type,
        source=source,
        user_id=user_id,
        local_date_berlin=local_date_berlin,
        payload=payload or {},
        happened_at=happened_at,
    )
