from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

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
