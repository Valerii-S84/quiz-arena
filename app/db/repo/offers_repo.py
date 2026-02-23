from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.offers_impressions import OfferImpression


class OffersRepo:
    @staticmethod
    async def get_by_idempotency_key(
        session: AsyncSession,
        *,
        user_id: int,
        idempotency_key: str,
    ) -> OfferImpression | None:
        stmt = select(OfferImpression).where(
            OfferImpression.user_id == user_id,
            OfferImpression.idempotency_key == idempotency_key,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_user_since(
        session: AsyncSession,
        *,
        user_id: int,
        shown_since_utc: datetime,
    ) -> list[OfferImpression]:
        stmt = (
            select(OfferImpression)
            .where(
                OfferImpression.user_id == user_id,
                OfferImpression.shown_at >= shown_since_utc,
            )
            .order_by(OfferImpression.shown_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def insert_impression_if_absent(
        session: AsyncSession,
        *,
        user_id: int,
        offer_code: str,
        trigger_code: str,
        priority: int,
        shown_at: datetime,
        local_date_berlin: date,
        idempotency_key: str,
    ) -> int | None:
        stmt = (
            pg_insert(OfferImpression)
            .values(
                user_id=user_id,
                offer_code=offer_code,
                trigger_code=trigger_code,
                priority=priority,
                shown_at=shown_at,
                local_date_berlin=local_date_berlin,
                idempotency_key=idempotency_key,
            )
            .on_conflict_do_nothing(index_elements=[OfferImpression.idempotency_key])
            .returning(OfferImpression.id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_dismissed(
        session: AsyncSession,
        *,
        user_id: int,
        impression_id: int,
        dismiss_reason: str,
        dismissed_at: datetime,
    ) -> bool:
        stmt = (
            update(OfferImpression)
            .where(
                OfferImpression.id == impression_id,
                OfferImpression.user_id == user_id,
            )
            .values(
                dismiss_reason=dismiss_reason,
                dismissed_at=dismissed_at,
            )
        )
        result = await session.execute(stmt)
        return bool(result.rowcount)

    @staticmethod
    async def mark_clicked(
        session: AsyncSession,
        *,
        user_id: int,
        impression_id: int,
        clicked_at: datetime,
    ) -> bool:
        stmt = (
            update(OfferImpression)
            .where(
                OfferImpression.id == impression_id,
                OfferImpression.user_id == user_id,
                OfferImpression.clicked_at.is_(None),
                OfferImpression.dismiss_reason.is_(None),
            )
            .values(clicked_at=clicked_at)
        )
        result = await session.execute(stmt)
        return bool(result.rowcount)

    @staticmethod
    async def mark_converted_purchase(
        session: AsyncSession,
        *,
        user_id: int,
        impression_id: int,
        purchase_id: UUID,
    ) -> bool:
        stmt = (
            update(OfferImpression)
            .where(
                OfferImpression.id == impression_id,
                OfferImpression.user_id == user_id,
                OfferImpression.converted_purchase_id.is_(None),
            )
            .values(converted_purchase_id=purchase_id)
        )
        result = await session.execute(stmt)
        return bool(result.rowcount)

    @staticmethod
    async def count_impressions_since(session: AsyncSession, *, shown_since_utc: datetime) -> int:
        stmt = select(func.count(OfferImpression.id)).where(
            OfferImpression.shown_at >= shown_since_utc
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_distinct_users_since(
        session: AsyncSession, *, shown_since_utc: datetime
    ) -> int:
        stmt = select(func.count(func.distinct(OfferImpression.user_id))).where(
            OfferImpression.shown_at >= shown_since_utc
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_clicked_since(session: AsyncSession, *, shown_since_utc: datetime) -> int:
        stmt = select(func.count(OfferImpression.id)).where(
            OfferImpression.shown_at >= shown_since_utc,
            OfferImpression.clicked_at.is_not(None),
            OfferImpression.dismiss_reason.is_(None),
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_dismissed_since(session: AsyncSession, *, shown_since_utc: datetime) -> int:
        stmt = select(func.count(OfferImpression.id)).where(
            OfferImpression.shown_at >= shown_since_utc,
            OfferImpression.dismiss_reason.is_not(None),
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_converted_since(session: AsyncSession, *, shown_since_utc: datetime) -> int:
        stmt = select(func.count(OfferImpression.id)).where(
            OfferImpression.shown_at >= shown_since_utc,
            OfferImpression.converted_purchase_id.is_not(None),
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_impressions_by_offer_code_since(
        session: AsyncSession,
        *,
        shown_since_utc: datetime,
        limit: int = 10,
    ) -> dict[str, int]:
        stmt = (
            select(OfferImpression.offer_code, func.count(OfferImpression.id))
            .where(OfferImpression.shown_at >= shown_since_utc)
            .group_by(OfferImpression.offer_code)
            .order_by(func.count(OfferImpression.id).desc(), OfferImpression.offer_code.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return {str(code): int(count) for code, count in result.all()}
