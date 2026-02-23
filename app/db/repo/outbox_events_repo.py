from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.outbox_events import OutboxEvent


class OutboxEventsRepo:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        event_type: str,
        payload: dict[str, object],
        status: str,
    ) -> OutboxEvent:
        event = OutboxEvent(
            event_type=event_type,
            payload=payload,
            status=status,
        )
        session.add(event)
        await session.flush()
        return event

    @staticmethod
    async def list_events_since(
        session: AsyncSession,
        *,
        since_utc: datetime,
        event_types: tuple[str, ...],
        limit: int,
    ) -> list[OutboxEvent]:
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.created_at >= since_utc,
                OutboxEvent.event_type.in_(event_types),
            )
            .order_by(OutboxEvent.created_at.desc(), OutboxEvent.id.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_status_since(
        session: AsyncSession,
        *,
        since_utc: datetime,
        event_types: tuple[str, ...],
    ) -> dict[str, int]:
        stmt = (
            select(OutboxEvent.status, func.count(OutboxEvent.id))
            .where(
                OutboxEvent.created_at >= since_utc,
                OutboxEvent.event_type.in_(event_types),
            )
            .group_by(OutboxEvent.status)
        )
        result = await session.execute(stmt)
        return {str(status): int(total) for status, total in result.all()}

    @staticmethod
    async def count_by_type_since(
        session: AsyncSession,
        *,
        since_utc: datetime,
        event_types: tuple[str, ...],
    ) -> dict[str, int]:
        stmt = (
            select(OutboxEvent.event_type, func.count(OutboxEvent.id))
            .where(
                OutboxEvent.created_at >= since_utc,
                OutboxEvent.event_type.in_(event_types),
            )
            .group_by(OutboxEvent.event_type)
        )
        result = await session.execute(stmt)
        return {str(event_type): int(total) for event_type, total in result.all()}

    @staticmethod
    async def delete_created_before(
        session: AsyncSession,
        *,
        cutoff_utc: datetime,
        limit: int,
    ) -> int:
        resolved_limit = max(1, int(limit))
        candidate_ids = (
            select(OutboxEvent.id)
            .where(OutboxEvent.created_at < cutoff_utc)
            .order_by(OutboxEvent.created_at.asc(), OutboxEvent.id.asc())
            .limit(resolved_limit)
            .scalar_subquery()
        )
        stmt = (
            delete(OutboxEvent).where(OutboxEvent.id.in_(candidate_ids)).returning(OutboxEvent.id)
        )
        result = await session.execute(stmt)
        return len(list(result.scalars()))
