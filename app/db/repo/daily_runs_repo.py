from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import and_, case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.daily_runs import DailyRun


class DailyRunsRepo:
    @staticmethod
    def _by_user_date_stmt(*, user_id: int, berlin_date: date):
        return (
            select(DailyRun)
            .where(
                DailyRun.user_id == user_id,
                DailyRun.berlin_date == berlin_date,
            )
            .order_by(
                case((DailyRun.status == "COMPLETED", 0), else_=1),
                DailyRun.started_at.desc(),
                DailyRun.id.desc(),
            )
            .limit(1)
        )

    @staticmethod
    async def get_by_id(session: AsyncSession, daily_run_id: UUID) -> DailyRun | None:
        return await session.get(DailyRun, daily_run_id)

    @staticmethod
    async def get_by_id_for_update(session: AsyncSession, daily_run_id: UUID) -> DailyRun | None:
        stmt = select(DailyRun).where(DailyRun.id == daily_run_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_user_date(
        session: AsyncSession,
        *,
        user_id: int,
        berlin_date: date,
    ) -> DailyRun | None:
        stmt = DailyRunsRepo._by_user_date_stmt(user_id=user_id, berlin_date=berlin_date)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_user_date_for_update(
        session: AsyncSession,
        *,
        user_id: int,
        berlin_date: date,
    ) -> DailyRun | None:
        stmt = DailyRunsRepo._by_user_date_stmt(
            user_id=user_id,
            berlin_date=berlin_date,
        ).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def has_completed_on_date(
        session: AsyncSession,
        *,
        user_id: int,
        berlin_date: date,
    ) -> bool:
        stmt = select(DailyRun.id).where(
            and_(
                DailyRun.user_id == user_id,
                DailyRun.berlin_date == berlin_date,
                DailyRun.status == "COMPLETED",
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def create(session: AsyncSession, *, daily_run: DailyRun) -> DailyRun:
        session.add(daily_run)
        await session.flush()
        return daily_run
