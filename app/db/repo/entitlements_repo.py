from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement


class EntitlementsRepo:
    @staticmethod
    async def has_active_premium(session: AsyncSession, user_id: int, now_utc: datetime) -> bool:
        stmt = select(Entitlement.id).where(
            and_(
                Entitlement.user_id == user_id,
                Entitlement.entitlement_type == "PREMIUM",
                Entitlement.status == "ACTIVE",
                Entitlement.starts_at <= now_utc,
                or_(Entitlement.ends_at.is_(None), Entitlement.ends_at > now_utc),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None
