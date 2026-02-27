from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import (
    DUEL_STATUS_CANCELED,
    DUEL_STATUS_EXPIRED,
    DUEL_TYPE_OPEN,
    normalize_duel_status,
)
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_create import create_friend_challenge
from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)


async def repost_friend_challenge_as_open(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError
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
    if challenge.creator_user_id != user_id:
        raise FriendChallengeAccessError
    if challenge.status != DUEL_STATUS_EXPIRED:
        raise FriendChallengeAccessError
    repost = await create_friend_challenge(
        session,
        creator_user_id=user_id,
        mode_code=challenge.mode_code,
        now_utc=now_utc,
        challenge_type=DUEL_TYPE_OPEN,
        total_rounds=challenge.total_rounds,
    )
    await emit_analytics_event(
        session,
        event_type="duel_reposted_as_open",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload={
            "source_challenge_id": str(challenge.id),
            "repost_challenge_id": str(repost.challenge_id),
            "format": repost.total_rounds,
        },
    )
    return repost


async def cancel_friend_challenge_by_creator(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError
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
    if challenge.creator_user_id != user_id:
        raise FriendChallengeAccessError
    if challenge.status != DUEL_STATUS_EXPIRED:
        raise FriendChallengeAccessError

    challenge.status = DUEL_STATUS_CANCELED
    challenge.completed_at = now_utc
    challenge.updated_at = now_utc
    await emit_analytics_event(
        session,
        event_type="duel_canceled_by_creator",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload={
            "challenge_id": str(challenge.id),
            "format": int(challenge.total_rounds),
        },
    )
    return _build_friend_challenge_snapshot(challenge)
