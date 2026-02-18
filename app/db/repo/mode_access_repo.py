from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.mode_access import ModeAccess


class ModeAccessRepo:
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
