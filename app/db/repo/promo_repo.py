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
    async def get_redemption_by_id(session: AsyncSession, redemption_id: UUID) -> PromoRedemption | None:
        return await session.get(PromoRedemption, redemption_id)

    @staticmethod
    async def get_redemption_by_idempotency_key(
        session: AsyncSession,
        idempotency_key: str,
    ) -> PromoRedemption | None:
        stmt = select(PromoRedemption).where(PromoRedemption.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
