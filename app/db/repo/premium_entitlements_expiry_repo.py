from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement


class PremiumEntitlementsExpiryRepo:
    @staticmethod
    async def count_expired_active_premium(
        session: AsyncSession,
        *,
        now_utc: datetime,
    ) -> int:
        stmt = select(func.count(Entitlement.id)).where(
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.status == "ACTIVE",
            Entitlement.ends_at.is_not(None),
            Entitlement.ends_at <= now_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one())

    @staticmethod
    async def expire_active_premium_before(
        session: AsyncSession,
        *,
        now_utc: datetime,
        limit: int,
    ) -> int:
        ids_stmt = (
            select(Entitlement.id)
            .where(
                Entitlement.entitlement_type == "PREMIUM",
                Entitlement.status == "ACTIVE",
                Entitlement.ends_at.is_not(None),
                Entitlement.ends_at <= now_utc,
            )
            .order_by(Entitlement.ends_at.asc(), Entitlement.id.asc())
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        ids_result = await session.execute(ids_stmt)
        entitlement_ids = [int(row_id) for row_id in ids_result.scalars().all()]
        if not entitlement_ids:
            return 0
        stmt = (
            update(Entitlement)
            .where(
                Entitlement.id.in_(entitlement_ids),
                Entitlement.entitlement_type == "PREMIUM",
                Entitlement.status == "ACTIVE",
                Entitlement.ends_at.is_not(None),
                Entitlement.ends_at <= now_utc,
            )
            .values(status="EXPIRED", updated_at=now_utc)
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)
