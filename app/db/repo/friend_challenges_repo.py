from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge


class FriendChallengesRepo:
    @staticmethod
    async def get_by_id(session: AsyncSession, challenge_id: UUID) -> FriendChallenge | None:
        return await session.get(FriendChallenge, challenge_id)

    @staticmethod
    async def get_by_id_for_update(session: AsyncSession, challenge_id: UUID) -> FriendChallenge | None:
        stmt = select(FriendChallenge).where(FriendChallenge.id == challenge_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_invite_token(session: AsyncSession, invite_token: str) -> FriendChallenge | None:
        stmt = select(FriendChallenge).where(FriendChallenge.invite_token == invite_token)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_invite_token_for_update(session: AsyncSession, invite_token: str) -> FriendChallenge | None:
        stmt = (
            select(FriendChallenge)
            .where(FriendChallenge.invite_token == invite_token)
            .with_for_update()
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, *, challenge: FriendChallenge) -> FriendChallenge:
        session.add(challenge)
        await session.flush()
        return challenge

    @staticmethod
    async def count_by_creator(
        session: AsyncSession,
        *,
        creator_user_id: int,
    ) -> int:
        stmt = select(func.count(FriendChallenge.id)).where(
            FriendChallenge.creator_user_id == creator_user_id
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_by_creator_access_type(
        session: AsyncSession,
        *,
        creator_user_id: int,
        access_type: str,
    ) -> int:
        stmt = select(func.count(FriendChallenge.id)).where(
            FriendChallenge.creator_user_id == creator_user_id,
            FriendChallenge.access_type == access_type,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def list_active_due_for_last_chance_for_update(
        session: AsyncSession,
        *,
        now_utc: datetime,
        expires_before_utc: datetime,
        limit: int,
    ) -> list[FriendChallenge]:
        resolved_limit = max(1, int(limit))
        stmt = (
            select(FriendChallenge)
            .where(
                FriendChallenge.status == "ACTIVE",
                FriendChallenge.expires_at > now_utc,
                FriendChallenge.expires_at <= expires_before_utc,
                FriendChallenge.expires_last_chance_notified_at.is_(None),
            )
            .order_by(FriendChallenge.expires_at.asc())
            .limit(resolved_limit)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_active_due_for_expire_for_update(
        session: AsyncSession,
        *,
        now_utc: datetime,
        limit: int,
    ) -> list[FriendChallenge]:
        resolved_limit = max(1, int(limit))
        stmt = (
            select(FriendChallenge)
            .where(
                FriendChallenge.status == "ACTIVE",
                FriendChallenge.expires_at <= now_utc,
            )
            .order_by(FriendChallenge.expires_at.asc())
            .limit(resolved_limit)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_series_id_for_update(
        session: AsyncSession,
        *,
        series_id: UUID,
    ) -> list[FriendChallenge]:
        stmt = (
            select(FriendChallenge)
            .where(FriendChallenge.series_id == series_id)
            .order_by(FriendChallenge.series_game_number.asc(), FriendChallenge.created_at.asc())
            .with_for_update()
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
