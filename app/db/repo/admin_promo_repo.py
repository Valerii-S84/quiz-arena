from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin_promo_code_usages import AdminPromoCodeUsage
from app.db.models.admin_promo_codes import AdminPromoCode


class AdminPromoRepo:
    @staticmethod
    async def get_by_id(session: AsyncSession, promo_id: UUID) -> AdminPromoCode | None:
        return await session.get(AdminPromoCode, promo_id)

    @staticmethod
    async def get_by_code(session: AsyncSession, code: str) -> AdminPromoCode | None:
        stmt = select(AdminPromoCode).where(AdminPromoCode.code == code)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, promo: AdminPromoCode) -> AdminPromoCode:
        session.add(promo)
        await session.flush()
        return promo

    @staticmethod
    async def bulk_create(
        session: AsyncSession,
        *,
        promos: Sequence[AdminPromoCode],
    ) -> list[AdminPromoCode]:
        session.add_all(promos)
        await session.flush()
        return list(promos)

    @staticmethod
    async def count_codes(session: AsyncSession, *, status: str | None = None) -> int:
        stmt = select(func.count(AdminPromoCode.id))
        if status:
            stmt = stmt.where(AdminPromoCode.status == status)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def list_codes(
        session: AsyncSession,
        *,
        status: str | None,
        page: int,
        limit: int,
    ) -> list[AdminPromoCode]:
        resolved_page = max(1, page)
        resolved_limit = max(1, min(200, limit))
        stmt = (
            select(AdminPromoCode)
            .order_by(AdminPromoCode.created_at.desc(), AdminPromoCode.id.desc())
            .offset((resolved_page - 1) * resolved_limit)
            .limit(resolved_limit)
        )
        if status:
            stmt = stmt.where(AdminPromoCode.status == status)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_usages(session: AsyncSession, *, promo_id: UUID) -> int:
        stmt = select(func.count(AdminPromoCodeUsage.id)).where(
            AdminPromoCodeUsage.promo_code_id == promo_id
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def list_usages(
        session: AsyncSession,
        *,
        promo_id: UUID,
        page: int,
        limit: int,
    ) -> list[AdminPromoCodeUsage]:
        resolved_page = max(1, page)
        resolved_limit = max(1, min(200, limit))
        stmt = (
            select(AdminPromoCodeUsage)
            .where(AdminPromoCodeUsage.promo_code_id == promo_id)
            .order_by(AdminPromoCodeUsage.used_at.desc(), AdminPromoCodeUsage.id.desc())
            .offset((resolved_page - 1) * resolved_limit)
            .limit(resolved_limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_status(
        session: AsyncSession,
        *,
        promo: AdminPromoCode,
        status: str,
        now_utc: datetime,
    ) -> AdminPromoCode:
        promo.status = status
        promo.updated_at = now_utc
        await session.flush()
        return promo

    @staticmethod
    async def update_fields(
        session: AsyncSession,
        *,
        promo: AdminPromoCode,
        now_utc: datetime,
        value: Decimal | None = None,
        max_uses: int | None = None,
        valid_until: datetime | None = None,
        channel_tag: str | None = None,
        status: str | None = None,
    ) -> AdminPromoCode:
        if value is not None:
            promo.value = value
        if max_uses is not None:
            promo.max_uses = max_uses
        if valid_until is not None:
            promo.valid_until = valid_until
        if channel_tag is not None:
            promo.channel_tag = channel_tag
        if status is not None:
            promo.status = status
        promo.updated_at = now_utc
        await session.flush()
        return promo
