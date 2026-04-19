from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo_queries import (
    DUEL_JOINED_STATUSES,
    DUEL_LIVE_STATUSES,
    challenge_one_or_none,
    count_challenges,
    for_update_due_stmt,
    list_challenge_rows,
    resolved_limit,
)


class FriendChallengesRepo:
    @staticmethod
    async def get_by_id(session: AsyncSession, challenge_id: UUID) -> FriendChallenge | None:
        return await session.get(FriendChallenge, challenge_id)

    @staticmethod
    async def get_by_id_for_update(
        session: AsyncSession, challenge_id: UUID
    ) -> FriendChallenge | None:
        stmt = select(FriendChallenge).where(FriendChallenge.id == challenge_id).with_for_update()
        return await challenge_one_or_none(session, stmt)

    @staticmethod
    async def get_by_invite_token(
        session: AsyncSession, invite_token: str
    ) -> FriendChallenge | None:
        stmt = select(FriendChallenge).where(FriendChallenge.invite_token == invite_token)
        return await challenge_one_or_none(session, stmt)

    @staticmethod
    async def get_by_invite_token_for_update(
        session: AsyncSession, invite_token: str
    ) -> FriendChallenge | None:
        stmt = (
            select(FriendChallenge)
            .where(FriendChallenge.invite_token == invite_token)
            .with_for_update()
        )
        return await challenge_one_or_none(session, stmt)

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
        conditions = [
            FriendChallenge.creator_user_id == creator_user_id,
            FriendChallenge.access_type == access_type,
            FriendChallenge.tournament_match_id.is_(None),
        ]
        if since is not None:
            conditions.append(FriendChallenge.created_at >= since)
        return await count_challenges(session, *conditions)

    @staticmethod
    async def count_live_for_user(
        session: AsyncSession,
        *,
        user_id: int,
    ) -> int:
        return await count_challenges(
            session,
            FriendChallenge.tournament_match_id.is_(None),
            FriendChallenge.status.in_(DUEL_LIVE_STATUSES),
            or_(
                FriendChallenge.creator_user_id == user_id,
                FriendChallenge.opponent_user_id == user_id,
            ),
        )

    @staticmethod
    async def count_live_open_by_creator(
        session: AsyncSession,
        *,
        creator_user_id: int,
    ) -> int:
        return await count_challenges(
            session,
            FriendChallenge.creator_user_id == creator_user_id,
            FriendChallenge.challenge_type == "OPEN",
            FriendChallenge.status.in_(DUEL_LIVE_STATUSES),
        )

    @staticmethod
    async def count_created_since(
        session: AsyncSession,
        *,
        creator_user_id: int,
        created_after_utc: datetime,
    ) -> int:
        return await count_challenges(
            session,
            FriendChallenge.tournament_match_id.is_(None),
            FriendChallenge.creator_user_id == creator_user_id,
            FriendChallenge.created_at >= created_after_utc,
        )

    @staticmethod
    async def list_recent_for_user(
        session: AsyncSession,
        *,
        user_id: int,
        limit: int,
    ) -> list[FriendChallenge]:
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
            .limit(resolved_limit(limit))
        )
        return await list_challenge_rows(session, stmt)

    @staticmethod
    async def list_active_due_for_last_chance_for_update(
        session: AsyncSession,
        *,
        now_utc: datetime,
        expires_before_utc: datetime,
        limit: int,
    ) -> list[FriendChallenge]:
        stmt = for_update_due_stmt(
            FriendChallenge.tournament_match_id.is_(None),
            FriendChallenge.status.in_(DUEL_JOINED_STATUSES),
            FriendChallenge.expires_at > now_utc,
            FriendChallenge.expires_at <= expires_before_utc,
            FriendChallenge.expires_last_chance_notified_at.is_(None),
            limit=limit,
        )
        return await list_challenge_rows(session, stmt)

    @staticmethod
    async def list_active_due_for_expire_for_update(
        session: AsyncSession,
        *,
        now_utc: datetime,
        limit: int,
    ) -> list[FriendChallenge]:
        stmt = for_update_due_stmt(
            FriendChallenge.tournament_match_id.is_(None),
            FriendChallenge.status.in_(DUEL_LIVE_STATUSES),
            FriendChallenge.expires_at <= now_utc,
            limit=limit,
        )
        return await list_challenge_rows(session, stmt)

    @staticmethod
    async def list_pending_due_for_expire_for_update(
        session: AsyncSession,
        *,
        now_utc: datetime,
        limit: int,
    ) -> list[FriendChallenge]:
        stmt = for_update_due_stmt(
            FriendChallenge.tournament_match_id.is_(None),
            FriendChallenge.status == "PENDING",
            FriendChallenge.expires_at <= now_utc,
            limit=limit,
        )
        return await list_challenge_rows(session, stmt)

    @staticmethod
    async def list_joined_due_for_walkover_for_update(
        session: AsyncSession,
        *,
        now_utc: datetime,
        limit: int,
    ) -> list[FriendChallenge]:
        stmt = for_update_due_stmt(
            FriendChallenge.tournament_match_id.is_(None),
            FriendChallenge.status.in_(DUEL_JOINED_STATUSES),
            FriendChallenge.opponent_user_id.is_not(None),
            FriendChallenge.expires_at <= now_utc,
            limit=limit,
        )
        return await list_challenge_rows(session, stmt)

    @staticmethod
    async def list_by_series_id_for_update(
        session: AsyncSession,
        *,
        series_id: UUID,
    ) -> list[FriendChallenge]:
        stmt = (
            select(FriendChallenge)
            .where(FriendChallenge.series_id == series_id)
            .order_by(
                FriendChallenge.series_game_number.asc(),
                FriendChallenge.created_at.asc(),
            )
            .with_for_update()
        )
        return await list_challenge_rows(session, stmt)
