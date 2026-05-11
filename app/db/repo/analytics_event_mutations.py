from __future__ import annotations

from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.analytics_constants import (
    ARENA_BEATEN_NOTIFICATION_EVENT_TYPES_SQL,
    ARENA_REVANCHE_EVENT_TYPES_SQL,
    DAILY_CUP_UNIQUE_PUSH_EVENT_TYPES_SQL,
)
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


async def create_arena_beaten_notification_event_once(
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
                sa.text("(payload ->> 'arena_duel_id')"),
                sa.text("(payload ->> 'previous_best_attempt_id')"),
                sa.text("(payload ->> 'new_best_attempt_id')"),
                sa.text("(payload ->> 'notification_type')"),
            ],
            index_where=sa.text(
                "user_id IS NOT NULL "
                "AND payload ? 'arena_duel_id' "
                "AND payload ? 'previous_best_attempt_id' "
                "AND payload ? 'new_best_attempt_id' "
                "AND payload ? 'notification_type' "
                "AND event_type IN "
                f"({ARENA_BEATEN_NOTIFICATION_EVENT_TYPES_SQL})"
            ),
        )
        .returning(AnalyticsEvent.id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def create_arena_revanche_event_once(
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
                sa.text("(payload ->> 'revanche_receiver_id')"),
                sa.text("(payload ->> 'source_attempt_id')"),
                sa.text("(payload ->> 'notification_type')"),
            ],
            index_where=sa.text(
                "user_id IS NOT NULL "
                "AND payload ? 'revanche_receiver_id' "
                "AND payload ? 'source_attempt_id' "
                "AND payload ? 'notification_type' "
                "AND event_type IN "
                f"({ARENA_REVANCHE_EVENT_TYPES_SQL})"
            ),
        )
        .returning(AnalyticsEvent.id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def delete_arena_revanche_events(
    session: AsyncSession,
    *,
    event_types: tuple[str, ...],
    user_id: int,
    payload: dict[str, object],
) -> int:
    stmt = delete(AnalyticsEvent).where(
        AnalyticsEvent.event_type.in_(event_types),
        AnalyticsEvent.user_id == user_id,
        AnalyticsEvent.payload["revanche_receiver_id"].astext
        == str(payload["revanche_receiver_id"]),
        AnalyticsEvent.payload["source_attempt_id"].astext == str(payload["source_attempt_id"]),
        AnalyticsEvent.payload["notification_type"].astext == str(payload["notification_type"]),
    )
    result = await session.execute(stmt)
    return int(getattr(result, "rowcount", 0) or 0)
