from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.analytics_constants import ARENA_REVANCHE_EVENT_TYPES
from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.friend_challenges import FriendChallenge

_DUEL_LIVE_STATUSES = ("ACTIVE", "PENDING", "ACCEPTED", "CREATOR_DONE", "OPPONENT_DONE")


class FriendChallengesRepoCoreMixin:
    @staticmethod
    async def get_by_id(session: AsyncSession, challenge_id: UUID) -> FriendChallenge | None:
        return await session.get(FriendChallenge, challenge_id)

    @staticmethod
    async def get_by_id_for_update(
        session: AsyncSession,
        challenge_id: UUID,
    ) -> FriendChallenge | None:
        stmt = select(FriendChallenge).where(FriendChallenge.id == challenge_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_invite_token(
        session: AsyncSession,
        invite_token: str,
    ) -> FriendChallenge | None:
        stmt = select(FriendChallenge).where(FriendChallenge.invite_token == invite_token)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_invite_token_for_update(
        session: AsyncSession,
        invite_token: str,
    ) -> FriendChallenge | None:
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
    async def count_by_creator_access_type(
        session: AsyncSession,
        *,
        creator_user_id: int,
        access_type: str,
        since: datetime | None = None,
    ) -> int:
        stmt = select(func.count(FriendChallenge.id)).where(
            FriendChallenge.creator_user_id == creator_user_id,
            FriendChallenge.access_type == access_type,
            FriendChallenge.tournament_match_id.is_(None),
        )
        if since is not None:
            stmt = stmt.where(FriendChallenge.created_at >= since)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_by_creator_access_type_excluding_arena_revanche(
        session: AsyncSession,
        *,
        creator_user_id: int,
        access_type: str,
        since: datetime | None = None,
    ) -> int:
        revanche_event_exists = (
            select(AnalyticsEvent.id)
            .where(
                AnalyticsEvent.user_id == creator_user_id,
                AnalyticsEvent.event_type.in_(ARENA_REVANCHE_EVENT_TYPES),
                AnalyticsEvent.payload["challenge_id"].astext == cast(FriendChallenge.id, String),
            )
            .exists()
        )
        stmt = select(func.count(FriendChallenge.id)).where(
            FriendChallenge.creator_user_id == creator_user_id,
            FriendChallenge.access_type == access_type,
            FriendChallenge.tournament_match_id.is_(None),
            ~revanche_event_exists,
        )
        if since is not None:
            stmt = stmt.where(FriendChallenge.created_at >= since)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_live_for_user(
        session: AsyncSession,
        *,
        user_id: int,
    ) -> int:
        stmt = select(func.count(FriendChallenge.id)).where(
            FriendChallenge.tournament_match_id.is_(None),
            FriendChallenge.status.in_(_DUEL_LIVE_STATUSES),
            or_(
                FriendChallenge.creator_user_id == user_id,
                FriendChallenge.opponent_user_id == user_id,
            ),
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_live_open_by_creator(
        session: AsyncSession,
        *,
        creator_user_id: int,
    ) -> int:
        stmt = select(func.count(FriendChallenge.id)).where(
            FriendChallenge.creator_user_id == creator_user_id,
            FriendChallenge.challenge_type == "OPEN",
            FriendChallenge.status.in_(_DUEL_LIVE_STATUSES),
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_created_since(
        session: AsyncSession,
        *,
        creator_user_id: int,
        created_after_utc: datetime,
    ) -> int:
        stmt = select(func.count(FriendChallenge.id)).where(
            FriendChallenge.tournament_match_id.is_(None),
            FriendChallenge.creator_user_id == creator_user_id,
            FriendChallenge.created_at >= created_after_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def list_recent_for_user(
        session: AsyncSession,
        *,
        user_id: int,
        limit: int,
    ) -> list[FriendChallenge]:
        resolved_limit = max(1, int(limit))
        stmt = (
            select(FriendChallenge)
            .where(
                FriendChallenge.tournament_match_id.is_(None),
                or_(
                    FriendChallenge.creator_user_id == user_id,
                    FriendChallenge.opponent_user_id == user_id,
                ),
            )
            .order_by(FriendChallenge.created_at.desc())
            .limit(resolved_limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
