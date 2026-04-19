from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import normalize_duel_status
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_expiry import (
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
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
    rows = await FriendChallengesRepo.list_recent_for_user(
        session,
        user_id=user_id,
        limit=limit,
    )
    snapshots: list[FriendChallengeSnapshot] = []
    for challenge in rows:
        challenge.status = normalize_duel_status(
            status=challenge.status,
            has_opponent=challenge.opponent_user_id is not None,
        )
        if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
            await _emit_friend_challenge_expired_event(
                session,
                challenge=challenge,
                happened_at=now_utc,
                source=EVENT_SOURCE_BOT,
            )
        snapshots.append(_build_friend_challenge_snapshot(challenge))
    return snapshots
