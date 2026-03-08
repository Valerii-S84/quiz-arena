from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_codes import PromoCode

from .promo_repo_admin_runtime_redemptions import (
    count_active_reserved_redemptions,
    count_redemptions,
    count_redemptions_by_status,
    list_recent_redemptions,
    list_redemptions,
    revoke_active_reserved_redemptions,
)


def _status_condition(*, status: str | None, now_utc: datetime):
    active_condition = and_(
        PromoCode.status == "ACTIVE",
        PromoCode.valid_until > now_utc,
        or_(PromoCode.max_total_uses.is_(None), PromoCode.used_total < PromoCode.max_total_uses),
    )
    expired_condition = or_(
        PromoCode.status.in_(("EXPIRED", "DEPLETED")),
        PromoCode.valid_until <= now_utc,
        and_(
            PromoCode.max_total_uses.is_not(None), PromoCode.used_total >= PromoCode.max_total_uses
        ),
    )
    if status == "active":
        return active_condition
    if status == "inactive":
        return PromoCode.status == "PAUSED"
    if status == "expired":
        return expired_condition
    return None


def _search_condition(*, query: str | None):
    if not query:
        return None
    term = f"%{query.strip()}%"
    return or_(
        PromoCode.code_prefix.ilike(term),
        PromoCode.campaign_name.ilike(term),
    )


class AdminRuntimePromoRepo:
    count_redemptions = staticmethod(count_redemptions)
    count_redemptions_by_status = staticmethod(count_redemptions_by_status)
    count_active_reserved_redemptions = staticmethod(count_active_reserved_redemptions)
    list_recent_redemptions = staticmethod(list_recent_redemptions)
    list_redemptions = staticmethod(list_redemptions)
    revoke_active_reserved_redemptions = staticmethod(revoke_active_reserved_redemptions)

    @staticmethod
    async def get_by_id(session: AsyncSession, promo_id: int) -> PromoCode | None:
        return await session.get(PromoCode, promo_id)

    @staticmethod
    async def get_by_id_for_update(session: AsyncSession, promo_id: int) -> PromoCode | None:
        stmt = select(PromoCode).where(PromoCode.id == promo_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_hash(session: AsyncSession, code_hash: str) -> PromoCode | None:
        stmt = select(PromoCode).where(PromoCode.code_hash == code_hash)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_existing_hashes(
        session: AsyncSession,
        *,
        code_hashes: Sequence[str],
    ) -> set[str]:
        if not code_hashes:
            return set()
        stmt = select(PromoCode.code_hash).where(PromoCode.code_hash.in_(tuple(code_hashes)))
        result = await session.execute(stmt)
        return {str(code_hash) for code_hash in result.scalars().all()}

    @staticmethod
    async def create(session: AsyncSession, *, promo: PromoCode) -> PromoCode:
        session.add(promo)
        await session.flush()
        return promo

    @staticmethod
    async def bulk_create(
        session: AsyncSession,
        *,
        promos: Sequence[PromoCode],
    ) -> list[PromoCode]:
        session.add_all(promos)
        await session.flush()
        return list(promos)

    @staticmethod
    async def count_codes(
        session: AsyncSession,
        *,
        status: str | None,
        query: str | None,
        now_utc: datetime,
    ) -> int:
        stmt = select(func.count(PromoCode.id))
        status_filter = _status_condition(status=status, now_utc=now_utc)
        search_filter = _search_condition(query=query)
        if status_filter is not None:
            stmt = stmt.where(status_filter)
        if search_filter is not None:
            stmt = stmt.where(search_filter)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def list_codes(
        session: AsyncSession,
        *,
        status: str | None,
        query: str | None,
        page: int,
        limit: int,
        now_utc: datetime,
    ) -> list[PromoCode]:
        resolved_page = max(1, page)
        resolved_limit = max(1, min(200, limit))
        stmt = (
            select(PromoCode)
            .order_by(PromoCode.updated_at.desc(), PromoCode.id.desc())
            .offset((resolved_page - 1) * resolved_limit)
            .limit(resolved_limit)
        )
        status_filter = _status_condition(status=status, now_utc=now_utc)
        search_filter = _search_condition(query=query)
        if status_filter is not None:
            stmt = stmt.where(status_filter)
        if search_filter is not None:
            stmt = stmt.where(search_filter)
        result = await session.execute(stmt)
        return list(result.scalars().all())
