from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.friend_challenges_repo import FriendChallengesRepo

from .friend_challenges_join_challenge_state import (
    FriendChallengeJoinState,
    load_joinable_friend_challenge_locked,
)


async def load_joinable_friend_challenge_by_token(
    session: AsyncSession,
    *,
    user_id: int,
    invite_token: str,
    now_utc: datetime,
) -> FriendChallengeJoinState:
    challenge = await FriendChallengesRepo.get_by_invite_token_for_update(session, invite_token)
    return await load_joinable_friend_challenge_locked(
        session,
        user_id=user_id,
        challenge=challenge,
        now_utc=now_utc,
    )


async def load_joinable_friend_challenge_by_id(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeJoinState:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    return await load_joinable_friend_challenge_locked(
        session,
        user_id=user_id,
        challenge=challenge,
        now_utc=now_utc,
    )
