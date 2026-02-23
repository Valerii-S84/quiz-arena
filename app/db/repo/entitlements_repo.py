from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement


class EntitlementsRepo:
    @staticmethod
    async def _get_active_premium_entitlement(
        session: AsyncSession,
        user_id: int,
        now_utc: datetime,
        for_update: bool = False,
    ) -> Entitlement | None:
        stmt = select(Entitlement).where(
            and_(
                Entitlement.user_id == user_id,
                Entitlement.entitlement_type == "PREMIUM",
                Entitlement.status == "ACTIVE",
                Entitlement.starts_at <= now_utc,
                or_(Entitlement.ends_at.is_(None), Entitlement.ends_at > now_utc),
            )
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def has_active_premium(session: AsyncSession, user_id: int, now_utc: datetime) -> bool:
        entitlement = await EntitlementsRepo._get_active_premium_entitlement(
            session, user_id, now_utc
        )
        return entitlement is not None

    @staticmethod
    async def get_active_premium_scope(
        session: AsyncSession,
        user_id: int,
        now_utc: datetime,
    ) -> str | None:
        entitlement = await EntitlementsRepo._get_active_premium_entitlement(
            session, user_id, now_utc
        )
        return entitlement.scope if entitlement is not None else None

    @staticmethod
    async def get_active_premium_for_update(
        session: AsyncSession,
        user_id: int,
        now_utc: datetime,
    ) -> Entitlement | None:
        return await EntitlementsRepo._get_active_premium_entitlement(
            session,
            user_id,
            now_utc,
            for_update=True,
        )

    @staticmethod
    async def create(session: AsyncSession, *, entitlement: Entitlement) -> Entitlement:
        session.add(entitlement)
        await session.flush()
        return entitlement

    @staticmethod
    async def has_recently_ended_premium_scope(
        session: AsyncSession,
        *,
        user_id: int,
        scope: str,
        since_utc: datetime,
        until_utc: datetime,
    ) -> bool:
        stmt = select(Entitlement.id).where(
            Entitlement.user_id == user_id,
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.scope == scope,
            Entitlement.status != "REVOKED",
            Entitlement.ends_at.is_not(None),
            Entitlement.ends_at >= since_utc,
            Entitlement.ends_at <= until_utc,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def has_active_premium_scope_ending_within(
        session: AsyncSession,
        *,
        user_id: int,
        scope: str,
        now_utc: datetime,
        until_utc: datetime,
    ) -> bool:
        stmt = select(Entitlement.id).where(
            and_(
                Entitlement.user_id == user_id,
                Entitlement.entitlement_type == "PREMIUM",
                Entitlement.scope == scope,
                Entitlement.status == "ACTIVE",
                Entitlement.starts_at <= now_utc,
                Entitlement.ends_at.is_not(None),
                Entitlement.ends_at > now_utc,
                Entitlement.ends_at <= until_utc,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None
