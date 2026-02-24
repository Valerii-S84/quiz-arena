from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.mode_access import ModeAccess


class ModeAccessRepo:
    @staticmethod
    async def get_by_idempotency_key(
        session: AsyncSession,
        *,
        idempotency_key: str,
    ) -> ModeAccess | None:
        stmt = select(ModeAccess).where(ModeAccess.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def has_active_access(
        session: AsyncSession,
        *,
        user_id: int,
        mode_code: str,
        now_utc: datetime,
    ) -> bool:
        stmt = select(ModeAccess.id).where(
            and_(
                ModeAccess.user_id == user_id,
                ModeAccess.mode_code == mode_code,
                ModeAccess.status == "ACTIVE",
                ModeAccess.starts_at <= now_utc,
                or_(ModeAccess.ends_at.is_(None), ModeAccess.ends_at > now_utc),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_latest_active_end(
        session: AsyncSession,
        *,
        user_id: int,
        mode_code: str,
        source: str,
        now_utc: datetime,
    ) -> datetime | None:
        stmt = (
            select(ModeAccess.ends_at)
            .where(
                and_(
                    ModeAccess.user_id == user_id,
                    ModeAccess.mode_code == mode_code,
                    ModeAccess.source == source,
                    ModeAccess.status == "ACTIVE",
                    ModeAccess.ends_at.is_not(None),
                    ModeAccess.ends_at > now_utc,
                )
            )
            .order_by(ModeAccess.ends_at.desc())
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, *, mode_access: ModeAccess) -> ModeAccess:
        session.add(mode_access)
        await session.flush()
        return mode_access

    @staticmethod
    async def revoke_active_by_purchase(
        session: AsyncSession,
        *,
        purchase_id: UUID,
        now_utc: datetime,
    ) -> int:
        stmt = (
            select(ModeAccess)
            .where(
                ModeAccess.source_purchase_id == purchase_id,
                ModeAccess.status == "ACTIVE",
            )
            .with_for_update()
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        for row in rows:
            row.status = "REVOKED"
            if row.ends_at is None or row.ends_at > now_utc:
                row.ends_at = now_utc
        if rows:
            await session.flush()
        return len(rows)
