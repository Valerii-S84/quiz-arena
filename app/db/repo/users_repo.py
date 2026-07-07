from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.streak_state import StreakState
from app.db.models.users import User
from app.db.repo.users_push_targets import (
    list_daily_cup_push_targets as _list_daily_cup_push_targets,
)
from app.db.repo.users_push_targets import (
    list_daily_cup_registered_reminder_targets as _list_daily_cup_registered_reminder_targets,
)
from app.db.repo.users_push_targets import list_daily_push_targets as _list_daily_push_targets


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
    async def get_id_by_telegram_user_id(
        session: AsyncSession, telegram_user_id: int
    ) -> int | None:
        stmt = select(User.id).where(User.telegram_user_id == telegram_user_id)
        result = await session.execute(stmt)
        user_id = result.scalar_one_or_none()
        return None if user_id is None else int(user_id)

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
        return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    async def touch_last_seen_by_telegram_user_id(
        session: AsyncSession,
        telegram_user_id: int,
        seen_at: datetime,
    ) -> User | None:
        stmt = (
            update(User)
            .where(User.telegram_user_id == telegram_user_id)
            .values(last_seen_at=seen_at)
            .returning(User)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_global_best_streak(session: AsyncSession) -> int:
        stmt = select(func.coalesce(func.max(StreakState.best_streak), 0))
        result = await session.execute(stmt)
        return int(result.scalar_one())

    list_daily_push_targets = staticmethod(_list_daily_push_targets)
    list_daily_cup_push_targets = staticmethod(_list_daily_cup_push_targets)
    list_daily_cup_registered_reminder_targets = staticmethod(
        _list_daily_cup_registered_reminder_targets
    )
