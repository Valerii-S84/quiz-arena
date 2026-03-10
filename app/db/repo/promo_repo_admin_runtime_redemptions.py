from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase


async def count_redemptions(session: AsyncSession, *, promo_id: int) -> int:
    stmt = select(func.count(PromoRedemption.id)).where(PromoRedemption.promo_code_id == promo_id)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_redemptions_by_status(
    session: AsyncSession,
    *,
    promo_id: int,
) -> dict[str, int]:
    stmt = (
        select(PromoRedemption.status, func.count(PromoRedemption.id))
        .where(PromoRedemption.promo_code_id == promo_id)
        .group_by(PromoRedemption.status)
    )
    result = await session.execute(stmt)
    return {str(status): int(count) for status, count in result.all()}


async def count_active_reserved_redemptions(
    session: AsyncSession,
    *,
    promo_id: int,
    now_utc: datetime,
) -> int:
    stmt = select(func.count(PromoRedemption.id)).where(
        PromoRedemption.promo_code_id == promo_id,
        PromoRedemption.status == "RESERVED",
        PromoRedemption.reserved_until.is_not(None),
        PromoRedemption.reserved_until > now_utc,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def list_recent_redemptions(
    session: AsyncSession,
    *,
    promo_id: int,
    limit: int = 20,
) -> list[tuple[PromoRedemption, str | None]]:
    stmt = (
        select(PromoRedemption, Purchase.product_code)
        .outerjoin(Purchase, Purchase.id == PromoRedemption.applied_purchase_id)
        .where(PromoRedemption.promo_code_id == promo_id)
        .order_by(PromoRedemption.updated_at.desc(), PromoRedemption.id.desc())
        .limit(max(1, min(limit, 100)))
    )
    result = await session.execute(stmt)
    return [(redemption, product_code) for redemption, product_code in result.all()]


async def list_redemptions(
    session: AsyncSession,
    *,
    promo_id: int,
    page: int,
    limit: int,
) -> list[PromoRedemption]:
    resolved_page = max(1, page)
    resolved_limit = max(1, min(200, limit))
    stmt = (
        select(PromoRedemption)
        .where(PromoRedemption.promo_code_id == promo_id)
        .order_by(PromoRedemption.updated_at.desc(), PromoRedemption.id.desc())
        .offset((resolved_page - 1) * resolved_limit)
        .limit(resolved_limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def revoke_active_reserved_redemptions(
    session: AsyncSession,
    *,
    promo_id: int,
    now_utc: datetime,
) -> list[PromoRedemption]:
    stmt = (
        select(PromoRedemption)
        .where(
            PromoRedemption.promo_code_id == promo_id,
            PromoRedemption.status == "RESERVED",
            PromoRedemption.reserved_until.is_not(None),
            PromoRedemption.reserved_until > now_utc,
        )
        .with_for_update()
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    for redemption in rows:
        redemption.status = "REVOKED"
        redemption.reserved_until = now_utc
        redemption.updated_at = now_utc
    return rows
