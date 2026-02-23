from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase


async def get_redemption_by_id(
    session: AsyncSession, redemption_id: UUID
) -> PromoRedemption | None:
    return await session.get(PromoRedemption, redemption_id)


async def get_redemption_by_id_for_update(
    session: AsyncSession,
    redemption_id: UUID,
) -> PromoRedemption | None:
    stmt = select(PromoRedemption).where(PromoRedemption.id == redemption_id).with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


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


async def revoke_redemption_for_refund(
    session: AsyncSession,
    *,
    purchase_id: UUID,
    promo_code_id: int,
    now_utc: datetime,
) -> tuple[PromoRedemption | None, PromoCode | None, bool]:
    redemption = await get_redemption_by_applied_purchase_id_for_update(
        session,
        applied_purchase_id=purchase_id,
    )
    promo_stmt = select(PromoCode).where(PromoCode.id == promo_code_id).with_for_update()
    promo_result = await session.execute(promo_stmt)
    promo_code = promo_result.scalar_one_or_none()

    was_revoked = False
    if redemption is not None and redemption.status != "REVOKED":
        redemption.status = "REVOKED"
        redemption.updated_at = now_utc
        was_revoked = True

    return redemption, promo_code, was_revoked


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


async def get_redemption_by_idempotency_key(
    session: AsyncSession,
    idempotency_key: str,
) -> PromoRedemption | None:
    stmt = select(PromoRedemption).where(PromoRedemption.idempotency_key == idempotency_key)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


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


async def create_redemption(
    session: AsyncSession, *, redemption: PromoRedemption
) -> PromoRedemption:
    session.add(redemption)
    await session.flush()
    return redemption


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
    return int(getattr(result, "rowcount", 0) or 0)


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
