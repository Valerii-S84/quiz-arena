from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_query_list import (
    list_friend_challenges_for_user as load_friend_challenge_snapshots_for_user,
)
from .friend_challenges_query_series import (
    get_friend_series_score_for_user as load_friend_series_score_for_user,
)
from .friend_challenges_query_state import load_friend_challenge_for_user
from .friend_challenges_records import _build_friend_challenge_snapshot


async def get_friend_challenge_snapshot_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    challenge = await load_friend_challenge_for_user(
        session,
        user_id=user_id,
        challenge_id=challenge_id,
        now_utc=now_utc,
    )
    return _build_friend_challenge_snapshot(challenge)


async def get_friend_series_score_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> tuple[int, int, int, int]:
    return await load_friend_series_score_for_user(
        session,
        user_id=user_id,
        challenge_id=challenge_id,
        now_utc=now_utc,
    )


async def list_friend_challenges_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
    limit: int = 20,
) -> list[FriendChallengeSnapshot]:
    return await load_friend_challenge_snapshots_for_user(
        session,
        user_id=user_id,
        now_utc=now_utc,
        limit=limit,
    )
