from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_codes import PromoCode


async def get_code_by_hash(session: AsyncSession, code_hash: str) -> PromoCode | None:
    stmt = select(PromoCode).where(PromoCode.code_hash == code_hash)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_code_by_hash_for_update(session: AsyncSession, code_hash: str) -> PromoCode | None:
    stmt = select(PromoCode).where(PromoCode.code_hash == code_hash).with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_code_by_id(session: AsyncSession, promo_code_id: int) -> PromoCode | None:
    return await session.get(PromoCode, promo_code_id)


async def get_code_by_id_for_update(session: AsyncSession, promo_code_id: int) -> PromoCode | None:
    stmt = select(PromoCode).where(PromoCode.id == promo_code_id).with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_codes(
    session: AsyncSession,
    *,
    status: str | None = None,
    campaign_name: str | None = None,
    limit: int = 50,
) -> list[PromoCode]:
    stmt = select(PromoCode).order_by(PromoCode.updated_at.desc(), PromoCode.id.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(PromoCode.status == status)
    if campaign_name:
        stmt = stmt.where(PromoCode.campaign_name == campaign_name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


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
    return int(getattr(result, "rowcount", 0) or 0)


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
    return int(getattr(result, "rowcount", 0) or 0)


async def count_campaigns_by_status(session: AsyncSession) -> dict[str, int]:
    stmt = select(PromoCode.status, func.count(PromoCode.id)).group_by(PromoCode.status)
    result = await session.execute(stmt)
    return {str(status): int(count) for status, count in result.all()}


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
    return int(getattr(result, "rowcount", 0) or 0)
