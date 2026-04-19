from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import normalize_duel_status
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_expiry import (
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)
from .friend_challenges_records import _build_friend_challenge_snapshot


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
