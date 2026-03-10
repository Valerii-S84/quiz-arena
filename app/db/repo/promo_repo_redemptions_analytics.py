from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption


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
