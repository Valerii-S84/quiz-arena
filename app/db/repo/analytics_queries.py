from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
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


async def has_arena_beaten_notification_event(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: int,
    payload: dict[str, object],
) -> bool:
    stmt = (
        select(AnalyticsEvent.id)
        .where(
            AnalyticsEvent.event_type == event_type,
            AnalyticsEvent.user_id == user_id,
            AnalyticsEvent.payload["arena_duel_id"].astext == str(payload["arena_duel_id"]),
            AnalyticsEvent.payload["previous_best_attempt_id"].astext
            == str(payload["previous_best_attempt_id"]),
            AnalyticsEvent.payload["new_best_attempt_id"].astext
            == str(payload["new_best_attempt_id"]),
            AnalyticsEvent.payload["notification_type"].astext == str(payload["notification_type"]),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def has_arena_revanche_event(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: int,
    payload: dict[str, object],
) -> bool:
    stmt = (
        select(AnalyticsEvent.id)
        .where(
            AnalyticsEvent.event_type == event_type,
            AnalyticsEvent.user_id == user_id,
            AnalyticsEvent.payload["revanche_receiver_id"].astext
            == str(payload["revanche_receiver_id"]),
            AnalyticsEvent.payload["source_attempt_id"].astext == str(payload["source_attempt_id"]),
            AnalyticsEvent.payload["notification_type"].astext == str(payload["notification_type"]),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def get_arena_revanche_event_payload(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: int,
    payload: dict[str, object],
) -> dict[str, object] | None:
    stmt = (
        select(AnalyticsEvent.payload)
        .where(
            AnalyticsEvent.event_type == event_type,
            AnalyticsEvent.user_id == user_id,
            AnalyticsEvent.payload["revanche_receiver_id"].astext
            == str(payload["revanche_receiver_id"]),
            AnalyticsEvent.payload["source_attempt_id"].astext == str(payload["source_attempt_id"]),
            AnalyticsEvent.payload["notification_type"].astext == str(payload["notification_type"]),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def count_user_events_since(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: int,
    since_utc: datetime,
) -> int:
    stmt = select(func.count(AnalyticsEvent.id)).where(
        AnalyticsEvent.event_type == event_type,
        AnalyticsEvent.user_id == user_id,
        AnalyticsEvent.happened_at >= since_utc,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)
