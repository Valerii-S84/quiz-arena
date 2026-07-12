from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.analytics_events import BERLIN_TIMEZONE, EVENT_SOURCE_WORKER
from app.db.repo.analytics_repo import AnalyticsRepo
from app.db.repo.production_reliability_repo import TelegramDeliveryAttemptsRepo
from app.db.session import SessionLocal
from app.services.telegram_delivery import TelegramDeliveryTarget


async def record_daily_cup_registration_push_sent(
    *,
    target: TelegramDeliveryTarget,
    user_id: int,
    event_type: str,
    tournament_id: str,
    happened_at: datetime,
    session_local: Any = SessionLocal,
) -> None:
    async with session_local.begin() as session:
        await AnalyticsRepo.create_daily_cup_push_event_once(
            session,
            event_type=event_type,
            source=EVENT_SOURCE_WORKER,
            user_id=user_id,
            local_date_berlin=happened_at.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date(),
            payload={"tournament_id": tournament_id},
            happened_at=happened_at,
        )
        sent = await TelegramDeliveryAttemptsRepo.mark_sent(
            session,
            idempotency_key=target.idempotency_key,
            sent_at=happened_at,
        )
        if sent != 1:
            raise RuntimeError("registration push delivery terminal lease was lost")


__all__ = ["record_daily_cup_registration_push_sent"]
