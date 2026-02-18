from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select, update
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
                clicked_at=dismissed_at,
            )
        )
        result = await session.execute(stmt)
        return bool(result.rowcount)
