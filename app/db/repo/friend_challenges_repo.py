from __future__ import annotations

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
