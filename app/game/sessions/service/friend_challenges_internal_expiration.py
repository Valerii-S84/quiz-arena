from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge

from .friend_challenges_expiry import (
    _emit_friend_challenge_expired_event as emit_friend_challenge_expired_event,
)
from .friend_challenges_expiry import (
    _expire_friend_challenge_if_due as expire_friend_challenge_if_due,
)
from .friend_challenges_records import _friend_challenge_expires_at as friend_challenge_expires_at
from .friend_challenges_records import (
    _friend_challenge_expires_at_accepted as friend_challenge_expires_at_accepted,
)


def _friend_challenge_expires_at(*, now_utc: datetime) -> datetime:
    return friend_challenge_expires_at(now_utc=now_utc)


def _friend_challenge_expires_at_accepted(*, now_utc: datetime) -> datetime:
    return friend_challenge_expires_at_accepted(now_utc=now_utc)


def _expire_friend_challenge_if_due(*, challenge: FriendChallenge, now_utc: datetime) -> bool:
    return expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc)


async def _emit_friend_challenge_expired_event(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    happened_at: datetime,
    source: str,
) -> None:
    await emit_friend_challenge_expired_event(
        session,
        challenge=challenge,
        happened_at=happened_at,
        source=source,
    )
