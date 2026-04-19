from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.game.sessions.types import FriendChallengeJoinResult

from .friend_challenges_join_analytics import emit_friend_challenge_joined_events
from .friend_challenges_join_state import (
    FriendChallengeJoinState,
    load_joinable_friend_challenge_by_id,
    load_joinable_friend_challenge_by_token,
)
from .friend_challenges_records import _build_friend_challenge_snapshot


async def join_friend_challenge_by_token(
    session: AsyncSession,
    *,
    user_id: int,
    invite_token: str,
    now_utc: datetime,
) -> FriendChallengeJoinResult:
    join_state = await load_joinable_friend_challenge_by_token(
        session,
        user_id=user_id,
        invite_token=invite_token,
        now_utc=now_utc,
    )
    return await _build_join_result(
        session,
        user_id=user_id,
        join_state=join_state,
        now_utc=now_utc,
    )


async def join_friend_challenge_by_id(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeJoinResult:
    join_state = await load_joinable_friend_challenge_by_id(
        session,
        user_id=user_id,
        challenge_id=challenge_id,
        now_utc=now_utc,
    )
    return await _build_join_result(
        session,
        user_id=user_id,
        join_state=join_state,
        now_utc=now_utc,
    )


async def _build_join_result(
    session: AsyncSession,
    *,
    user_id: int,
    join_state: FriendChallengeJoinState,
    now_utc: datetime,
) -> FriendChallengeJoinResult:
    if join_state.joined_now:
        await emit_friend_challenge_joined_events(
            session,
            challenge=join_state.challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
            user_id=user_id,
        )
    return FriendChallengeJoinResult(
        snapshot=_build_friend_challenge_snapshot(join_state.challenge),
        joined_now=join_state.joined_now,
    )
