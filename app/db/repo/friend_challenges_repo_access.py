from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo_queries import (
    challenge_one_or_none,
    list_challenge_rows,
    resolved_limit,
)


async def get_by_id(session: AsyncSession, challenge_id: UUID) -> FriendChallenge | None:
    return await session.get(FriendChallenge, challenge_id)


async def get_by_id_for_update(
    session: AsyncSession,
    challenge_id: UUID,
) -> FriendChallenge | None:
    stmt = select(FriendChallenge).where(FriendChallenge.id == challenge_id).with_for_update()
    return await challenge_one_or_none(session, stmt)


async def get_by_invite_token(
    session: AsyncSession,
    invite_token: str,
) -> FriendChallenge | None:
    stmt = select(FriendChallenge).where(FriendChallenge.invite_token == invite_token)
    return await challenge_one_or_none(session, stmt)


async def get_by_invite_token_for_update(
    session: AsyncSession,
    invite_token: str,
) -> FriendChallenge | None:
    stmt = (
        select(FriendChallenge)
        .where(FriendChallenge.invite_token == invite_token)
        .with_for_update()
    )
    return await challenge_one_or_none(session, stmt)


async def create(session: AsyncSession, *, challenge: FriendChallenge) -> FriendChallenge:
    session.add(challenge)
    await session.flush()
    return challenge


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
