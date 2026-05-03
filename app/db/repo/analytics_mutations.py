from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from hashlib import sha256

import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.analytics_constants import (
    ARENA_BEATEN_NOTIFICATION_EVENT_TYPES_SQL,
    ARENA_REVANCHE_EVENT_TYPES_SQL,
    DAILY_CUP_UNIQUE_PUSH_EVENT_TYPES_SQL,
)
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


async def lock_arena_beaten_notification_event_key(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: int,
    payload: dict[str, object],
) -> None:
    dedupe_key = "|".join(
        (
            event_type,
            str(user_id),
            str(payload["arena_duel_id"]),
            str(payload["previous_best_attempt_id"]),
            str(payload["new_best_attempt_id"]),
            str(payload["notification_type"]),
        )
    )
    digest = sha256(dedupe_key.encode("utf-8")).digest()
    lock_key_1 = int.from_bytes(digest[:4], byteorder="big", signed=True)
    lock_key_2 = int.from_bytes(digest[4:8], byteorder="big", signed=True)
    await session.execute(
        sa.text("SELECT pg_advisory_xact_lock(:lock_key_1, :lock_key_2)"),
        {"lock_key_1": lock_key_1, "lock_key_2": lock_key_2},
    )


async def lock_arena_revanche_event_key(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: int,
    payload: dict[str, object],
) -> None:
    dedupe_key = "|".join(
        (
            event_type,
            str(user_id),
            str(payload["revanche_receiver_id"]),
            str(payload["source_attempt_id"]),
            str(payload["notification_type"]),
        )
    )
    digest = sha256(dedupe_key.encode("utf-8")).digest()
    lock_key_1 = int.from_bytes(digest[:4], byteorder="big", signed=True)
    lock_key_2 = int.from_bytes(digest[4:8], byteorder="big", signed=True)
    await session.execute(
        sa.text("SELECT pg_advisory_xact_lock(:lock_key_1, :lock_key_2)"),
        {"lock_key_1": lock_key_1, "lock_key_2": lock_key_2},
    )


async def lock_arena_revanche_sender_quota(
    session: AsyncSession,
    *,
    user_id: int,
) -> None:
    dedupe_key = "|".join(("arena_revanche_sender_quota", str(user_id)))
    digest = sha256(dedupe_key.encode("utf-8")).digest()
    lock_key_1 = int.from_bytes(digest[:4], byteorder="big", signed=True)
    lock_key_2 = int.from_bytes(digest[4:8], byteorder="big", signed=True)
    await session.execute(
        sa.text("SELECT pg_advisory_xact_lock(:lock_key_1, :lock_key_2)"),
        {"lock_key_1": lock_key_1, "lock_key_2": lock_key_2},
    )


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
