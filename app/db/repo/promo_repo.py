from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption


class PromoRepo:
    @staticmethod
    async def get_code_by_hash(session: AsyncSession, code_hash: str) -> PromoCode | None:
        stmt = select(PromoCode).where(PromoCode.code_hash == code_hash)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_code_by_id(session: AsyncSession, promo_code_id: int) -> PromoCode | None:
        return await session.get(PromoCode, promo_code_id)

    @staticmethod
    async def get_code_by_id_for_update(session: AsyncSession, promo_code_id: int) -> PromoCode | None:
        stmt = select(PromoCode).where(PromoCode.id == promo_code_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_redemption_by_id(session: AsyncSession, redemption_id: UUID) -> PromoRedemption | None:
        return await session.get(PromoRedemption, redemption_id)

    @staticmethod
    async def get_redemption_by_id_for_update(
        session: AsyncSession,
        redemption_id: UUID,
    ) -> PromoRedemption | None:
        stmt = select(PromoRedemption).where(PromoRedemption.id == redemption_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_redemption_by_applied_purchase_id_for_update(
        session: AsyncSession,
        applied_purchase_id: UUID,
    ) -> PromoRedemption | None:
        stmt = (
            select(PromoRedemption)
            .where(PromoRedemption.applied_purchase_id == applied_purchase_id)
            .with_for_update()
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_redemption_by_idempotency_key(
        session: AsyncSession,
        idempotency_key: str,
    ) -> PromoRedemption | None:
        stmt = select(PromoRedemption).where(PromoRedemption.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
