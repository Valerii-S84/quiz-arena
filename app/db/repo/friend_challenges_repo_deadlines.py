from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge

from .friend_challenges_repo_core import _DUEL_LIVE_STATUSES


class FriendChallengesRepoDeadlineMixin:
    @staticmethod
    async def mark_daily_cup_turn_reminders_notified(
        session: AsyncSession,
        *,
        challenge_ids: set[UUID],
        notified_at: datetime,
    ) -> None:
        if not challenge_ids:
            return
        await session.execute(
            update(FriendChallenge)
            .where(FriendChallenge.id.in_(challenge_ids))
            .values(
                expires_last_chance_notified_at=notified_at,
                updated_at=notified_at,
            )
        )

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
                FriendChallenge.tournament_match_id.is_(None),
                FriendChallenge.status.in_(
                    ("PENDING", "ACCEPTED", "CREATOR_DONE", "OPPONENT_DONE", "ACTIVE")
                ),
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
                FriendChallenge.tournament_match_id.is_(None),
                FriendChallenge.status.in_(_DUEL_LIVE_STATUSES),
                FriendChallenge.expires_at <= now_utc,
            )
            .order_by(FriendChallenge.expires_at.asc())
            .limit(resolved_limit)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_pending_due_for_expire_for_update(
        session: AsyncSession,
        *,
        now_utc: datetime,
        limit: int,
    ) -> list[FriendChallenge]:
        resolved_limit = max(1, int(limit))
        stmt = (
            select(FriendChallenge)
            .where(
                FriendChallenge.tournament_match_id.is_(None),
                FriendChallenge.status == "PENDING",
                FriendChallenge.expires_at <= now_utc,
            )
            .order_by(FriendChallenge.expires_at.asc())
            .limit(resolved_limit)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_joined_due_for_walkover_for_update(
        session: AsyncSession,
        *,
        now_utc: datetime,
        limit: int,
    ) -> list[FriendChallenge]:
        resolved_limit = max(1, int(limit))
        stmt = (
            select(FriendChallenge)
            .where(
                FriendChallenge.tournament_match_id.is_(None),
                FriendChallenge.status.in_(("ACCEPTED", "CREATOR_DONE", "OPPONENT_DONE", "ACTIVE")),
                FriendChallenge.opponent_user_id.is_not(None),
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
            .order_by(
                FriendChallenge.series_game_number.asc(),
                FriendChallenge.created_at.asc(),
            )
            .with_for_update()
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
