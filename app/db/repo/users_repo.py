from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.daily_push_logs import DailyPushLog
from app.db.models.daily_runs import DailyRun
from app.db.models.streak_state import StreakState
from app.db.models.users import User


class UsersRepo:
    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
        return await session.get(User, user_id)

    @staticmethod
    async def get_by_id_for_update(session: AsyncSession, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_telegram_user_id(session: AsyncSession, telegram_user_id: int) -> User | None:
        stmt = select(User).where(User.telegram_user_id == telegram_user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_referral_code(session: AsyncSession, referral_code: str) -> User | None:
        stmt = select(User).where(User.referral_code == referral_code)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_ids(
        session: AsyncSession,
        user_ids: Sequence[int],
    ) -> list[User]:
        ids = tuple({int(user_id) for user_id in user_ids})
        if not ids:
            return []
        stmt = select(User).where(User.id.in_(ids))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        telegram_user_id: int,
        referral_code: str,
        username: str | None,
        first_name: str | None,
        referred_by_user_id: int | None,
        language_code: str = "de",
        timezone: str = "Europe/Berlin",
    ) -> User:
        user = User(
            telegram_user_id=telegram_user_id,
            referral_code=referral_code,
            username=username,
            first_name=first_name,
            referred_by_user_id=referred_by_user_id,
            language_code=language_code,
            timezone=timezone,
            status="ACTIVE",
        )
        session.add(user)
        await session.flush()
        return user

    @staticmethod
    async def touch_last_seen(session: AsyncSession, user_id: int, seen_at: datetime) -> int:
        stmt = update(User).where(User.id == user_id).values(last_seen_at=seen_at)
        result = await session.execute(stmt)
        return result.rowcount or 0

    @staticmethod
    async def list_daily_push_targets(
        session: AsyncSession,
        *,
        berlin_date: date,
        after_user_id: int | None,
        limit: int,
    ) -> list[tuple[int, int, int]]:
        resolved_limit = max(1, min(1000, int(limit)))
        completed_daily_exists = (
            select(DailyRun.id)
            .where(
                DailyRun.user_id == User.id,
                DailyRun.berlin_date == berlin_date,
                DailyRun.status == "COMPLETED",
            )
            .exists()
        )
        push_logged_exists = (
            select(DailyPushLog.user_id)
            .where(
                DailyPushLog.user_id == User.id,
                DailyPushLog.berlin_date == berlin_date,
            )
            .exists()
        )
        stmt = (
            select(
                User.id,
                User.telegram_user_id,
                func.coalesce(StreakState.current_streak, 0),
            )
            .outerjoin(StreakState, StreakState.user_id == User.id)
            .where(User.status == "ACTIVE", ~completed_daily_exists, ~push_logged_exists)
            .order_by(User.id.asc())
            .limit(resolved_limit)
        )
        if after_user_id is not None:
            stmt = stmt.where(User.id > after_user_id)

        result = await session.execute(stmt)
        rows: list[tuple[int, int, int]] = []
        for user_id_raw, telegram_user_id_raw, streak_raw in result.all():
            rows.append(
                (
                    int(user_id_raw),
                    int(telegram_user_id_raw),
                    int(streak_raw),
                )
            )
        return rows
