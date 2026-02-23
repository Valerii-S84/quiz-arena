from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import distinct, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_attempts import PromoAttempt
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase


class PromoRepo:
    @staticmethod
    async def get_code_by_hash(session: AsyncSession, code_hash: str) -> PromoCode | None:
        stmt = select(PromoCode).where(PromoCode.code_hash == code_hash)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_code_by_hash_for_update(
        session: AsyncSession, code_hash: str
    ) -> PromoCode | None:
        stmt = select(PromoCode).where(PromoCode.code_hash == code_hash).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_code_by_id(session: AsyncSession, promo_code_id: int) -> PromoCode | None:
        return await session.get(PromoCode, promo_code_id)

    @staticmethod
    async def get_code_by_id_for_update(
        session: AsyncSession, promo_code_id: int
    ) -> PromoCode | None:
        stmt = select(PromoCode).where(PromoCode.id == promo_code_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_codes(
        session: AsyncSession,
        *,
        status: str | None = None,
        campaign_name: str | None = None,
        limit: int = 50,
    ) -> list[PromoCode]:
        stmt = (
            select(PromoCode)
            .order_by(PromoCode.updated_at.desc(), PromoCode.id.desc())
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(PromoCode.status == status)
        if campaign_name:
            stmt = stmt.where(PromoCode.campaign_name == campaign_name)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_redemption_by_id(
        session: AsyncSession, redemption_id: UUID
    ) -> PromoRedemption | None:
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
    async def revoke_redemption_for_refund(
        session: AsyncSession,
        *,
        purchase_id: UUID,
        promo_code_id: int,
        now_utc: datetime,
    ) -> tuple[PromoRedemption | None, PromoCode | None, bool]:
        redemption = await PromoRepo.get_redemption_by_applied_purchase_id_for_update(
            session,
            applied_purchase_id=purchase_id,
        )
        promo_code = await PromoRepo.get_code_by_id_for_update(session, promo_code_id)

        was_revoked = False
        if redemption is not None and redemption.status != "REVOKED":
            redemption.status = "REVOKED"
            redemption.updated_at = now_utc
            was_revoked = True

        return redemption, promo_code, was_revoked

    @staticmethod
    async def get_refunded_purchase_ids_with_pending_redemption_revoke(
        session: AsyncSession,
        *,
        limit: int = 100,
    ) -> list[UUID]:
        stmt = (
            select(PromoRedemption.applied_purchase_id)
            .join(Purchase, Purchase.id == PromoRedemption.applied_purchase_id)
            .where(
                PromoRedemption.applied_purchase_id.is_not(None),
                PromoRedemption.status != "REVOKED",
                Purchase.status == "REFUNDED",
                Purchase.applied_promo_code_id.is_not(None),
            )
            .order_by(Purchase.refunded_at.asc().nullsfirst(), Purchase.id.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [purchase_id for purchase_id in result.scalars().all() if purchase_id is not None]

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
        stmt = (
            select(PromoRedemption)
            .where(PromoRedemption.idempotency_key == idempotency_key)
            .with_for_update()
        )
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
    async def create_redemption(
        session: AsyncSession, *, redemption: PromoRedemption
    ) -> PromoRedemption:
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
    async def count_attempts_by_result(
        session: AsyncSession,
        *,
        since_utc: datetime,
    ) -> dict[str, int]:
        stmt = (
            select(PromoAttempt.result, func.count(PromoAttempt.id))
            .where(PromoAttempt.attempted_at >= since_utc)
            .group_by(PromoAttempt.result)
        )
        result = await session.execute(stmt)
        return {str(status): int(count) for status, count in result.all()}

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

    @staticmethod
    async def count_redemptions_by_status(
        session: AsyncSession,
        *,
        since_utc: datetime,
    ) -> dict[str, int]:
        stmt = (
            select(PromoRedemption.status, func.count(PromoRedemption.id))
            .where(PromoRedemption.created_at >= since_utc)
            .group_by(PromoRedemption.status)
        )
        result = await session.execute(stmt)
        return {str(status): int(count) for status, count in result.all()}

    @staticmethod
    async def count_discount_redemptions_by_status(
        session: AsyncSession,
        *,
        since_utc: datetime,
    ) -> dict[str, int]:
        stmt = (
            select(PromoRedemption.status, func.count(PromoRedemption.id))
            .join(PromoCode, PromoCode.id == PromoRedemption.promo_code_id)
            .where(
                PromoRedemption.created_at >= since_utc,
                PromoCode.promo_type == "PERCENT_DISCOUNT",
            )
            .group_by(PromoRedemption.status)
        )
        result = await session.execute(stmt)
        return {str(status): int(count) for status, count in result.all()}

    @staticmethod
    async def count_campaigns_by_status(session: AsyncSession) -> dict[str, int]:
        stmt = select(PromoCode.status, func.count(PromoCode.id)).group_by(PromoCode.status)
        result = await session.execute(stmt)
        return {str(status): int(count) for status, count in result.all()}

    @staticmethod
    async def count_paused_campaigns_since(
        session: AsyncSession,
        *,
        since_utc: datetime,
    ) -> int:
        stmt = select(func.count(PromoCode.id)).where(
            PromoCode.status == "PAUSED",
            PromoCode.updated_at >= since_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def get_abusive_code_hashes(
        session: AsyncSession,
        *,
        since_utc: datetime,
        min_failed_attempts: int,
        min_distinct_users: int,
    ) -> list[str]:
        stmt = (
            select(PromoAttempt.normalized_code_hash)
            .where(
                PromoAttempt.attempted_at >= since_utc,
                PromoAttempt.result.in_(("INVALID", "EXPIRED", "NOT_APPLICABLE")),
            )
            .group_by(PromoAttempt.normalized_code_hash)
            .having(
                func.count(PromoAttempt.id) > min_failed_attempts,
                func.count(distinct(PromoAttempt.user_id)) >= min_distinct_users,
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_abusive_code_hashes(
        session: AsyncSession,
        *,
        since_utc: datetime,
        min_failed_attempts: int,
        min_distinct_users: int,
    ) -> int:
        code_hashes = await PromoRepo.get_abusive_code_hashes(
            session,
            since_utc=since_utc,
            min_failed_attempts=min_failed_attempts,
            min_distinct_users=min_distinct_users,
        )
        return len(code_hashes)

    @staticmethod
    async def pause_active_codes_by_hashes(
        session: AsyncSession,
        *,
        code_hashes: list[str],
        now_utc: datetime,
    ) -> int:
        if not code_hashes:
            return 0

        stmt = (
            update(PromoCode)
            .where(
                PromoCode.code_hash.in_(code_hashes),
                PromoCode.status == "ACTIVE",
            )
            .values(status="PAUSED", updated_at=now_utc)
        )
        result = await session.execute(stmt)
        return int(result.rowcount or 0)
