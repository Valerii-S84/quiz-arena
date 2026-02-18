from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_attempts import PromoAttempt
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption


class PromoRepo:
    @staticmethod
    async def get_code_by_hash(session: AsyncSession, code_hash: str) -> PromoCode | None:
        stmt = select(PromoCode).where(PromoCode.code_hash == code_hash)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_code_by_hash_for_update(session: AsyncSession, code_hash: str) -> PromoCode | None:
        stmt = select(PromoCode).where(PromoCode.code_hash == code_hash).with_for_update()
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

    @staticmethod
    async def get_redemption_by_idempotency_key_for_update(
        session: AsyncSession,
        idempotency_key: str,
    ) -> PromoRedemption | None:
        stmt = select(PromoRedemption).where(PromoRedemption.idempotency_key == idempotency_key).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_redemption_by_code_and_user_for_update(
        session: AsyncSession,
        *,
        promo_code_id: int,
        user_id: int,
    ) -> PromoRedemption | None:
        stmt = (
            select(PromoRedemption)
            .where(
                PromoRedemption.promo_code_id == promo_code_id,
                PromoRedemption.user_id == user_id,
            )
            .with_for_update()
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_redemption(session: AsyncSession, *, redemption: PromoRedemption) -> PromoRedemption:
        session.add(redemption)
        await session.flush()
        return redemption

    @staticmethod
    async def create_attempt(session: AsyncSession, *, attempt: PromoAttempt) -> PromoAttempt:
        session.add(attempt)
        await session.flush()
        return attempt

    @staticmethod
    async def count_user_attempts(
        session: AsyncSession,
        *,
        user_id: int,
        since_utc: datetime,
        attempt_results: Iterable[str] | None = None,
    ) -> int:
        stmt = select(func.count(PromoAttempt.id)).where(
            PromoAttempt.user_id == user_id,
            PromoAttempt.attempted_at >= since_utc,
        )
        if attempt_results is not None:
            values = tuple(attempt_results)
            if not values:
                return 0
            stmt = stmt.where(PromoAttempt.result.in_(values))

        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def get_last_user_attempt_at(
        session: AsyncSession,
        *,
        user_id: int,
        since_utc: datetime,
        attempt_results: Iterable[str] | None = None,
    ) -> datetime | None:
        stmt = select(func.max(PromoAttempt.attempted_at)).where(
            PromoAttempt.user_id == user_id,
            PromoAttempt.attempted_at >= since_utc,
        )
        if attempt_results is not None:
            values = tuple(attempt_results)
            if not values:
                return None
            stmt = stmt.where(PromoAttempt.result.in_(values))

        result = await session.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def expire_reserved_redemptions(session: AsyncSession, *, now_utc: datetime) -> int:
        stmt = (
            update(PromoRedemption)
            .where(
                PromoRedemption.status == "RESERVED",
                PromoRedemption.reserved_until.is_not(None),
                PromoRedemption.reserved_until <= now_utc,
            )
            .values(status="EXPIRED", updated_at=now_utc)
        )
        result = await session.execute(stmt)
        return int(result.rowcount or 0)

    @staticmethod
    async def expire_active_codes(session: AsyncSession, *, now_utc: datetime) -> int:
        stmt = (
            update(PromoCode)
            .where(
                PromoCode.status == "ACTIVE",
                PromoCode.valid_until <= now_utc,
            )
            .values(status="EXPIRED", updated_at=now_utc)
        )
        result = await session.execute(stmt)
        return int(result.rowcount or 0)

    @staticmethod
    async def deplete_active_codes(session: AsyncSession, *, now_utc: datetime) -> int:
        stmt = (
            update(PromoCode)
            .where(
                PromoCode.status == "ACTIVE",
                PromoCode.max_total_uses.is_not(None),
                PromoCode.used_total >= PromoCode.max_total_uses,
            )
            .values(status="DEPLETED", updated_at=now_utc)
        )
        result = await session.execute(stmt)
        return int(result.rowcount or 0)
