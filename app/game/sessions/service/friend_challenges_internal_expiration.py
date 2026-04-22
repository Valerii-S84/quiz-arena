from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.game.friend_challenges.constants import (
    DUEL_STATUS_EXPIRED,
    DUEL_STATUS_PENDING,
    DUEL_STATUS_WALKOVER,
    is_duel_active_status,
    normalize_duel_status,
)

from .constants import DUEL_ACCEPTED_TTL_SECONDS, DUEL_PENDING_TTL_SECONDS
from .friend_challenges_analytics import (
    _emit_friend_challenge_expired_event as _emit_friend_challenge_expired_event_analytics,
)


def _friend_challenge_expires_at(*, now_utc: datetime) -> datetime:
    return now_utc + timedelta(seconds=DUEL_PENDING_TTL_SECONDS)


def _friend_challenge_expires_at_accepted(*, now_utc: datetime) -> datetime:
    return now_utc + timedelta(seconds=DUEL_ACCEPTED_TTL_SECONDS)


def _expire_friend_challenge_if_due(*, challenge: FriendChallenge, now_utc: datetime) -> bool:
    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=challenge.opponent_user_id is not None,
    )
    if not is_duel_active_status(challenge.status):
        return False
    if challenge.expires_at > now_utc:
        return False

    if challenge.status == DUEL_STATUS_PENDING:
        challenge.status = DUEL_STATUS_EXPIRED
        challenge.winner_user_id = None
        challenge.completed_at = now_utc
        challenge.updated_at = now_utc
        return True

    creator_done = challenge.creator_finished_at is not None or (
        challenge.creator_answered_round >= challenge.total_rounds
    )
    opponent_done = challenge.opponent_finished_at is not None or (
        challenge.opponent_answered_round >= challenge.total_rounds
    )
    if creator_done and not opponent_done:
        challenge.winner_user_id = challenge.creator_user_id
        challenge.opponent_score = 0
    elif opponent_done and not creator_done:
        challenge.winner_user_id = challenge.opponent_user_id
        challenge.creator_score = 0
    else:
        challenge.winner_user_id = None
        challenge.creator_score = 0
        challenge.opponent_score = 0
    challenge.status = DUEL_STATUS_WALKOVER
    challenge.completed_at = now_utc
    challenge.updated_at = now_utc
    return True


async def _emit_friend_challenge_expired_event(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    happened_at: datetime,
    source: str,
) -> None:
    await _emit_friend_challenge_expired_event_analytics(
        session,
        challenge=challenge,
        happened_at=happened_at,
        source=source,
    )
