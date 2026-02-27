from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import (
    DUEL_STATUS_ACCEPTED,
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_LEGACY_ACTIVE,
    DUEL_STATUS_OPPONENT_DONE,
    DUEL_STATUS_PENDING,
    normalize_duel_status,
)
from app.game.sessions.errors import (
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.types import FriendChallengeJoinResult

from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
    _friend_challenge_expires_at_accepted,
)


async def join_friend_challenge_by_token(
    session: AsyncSession,
    *,
    user_id: int,
    invite_token: str,
    now_utc: datetime,
) -> FriendChallengeJoinResult:
    challenge = await FriendChallengesRepo.get_by_invite_token_for_update(session, invite_token)
    return await _join_friend_challenge_locked(
        session, user_id=user_id, challenge=challenge, now_utc=now_utc
    )


async def join_friend_challenge_by_id(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeJoinResult:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    return await _join_friend_challenge_locked(
        session, user_id=user_id, challenge=challenge, now_utc=now_utc
    )


async def _join_friend_challenge_locked(
    session: AsyncSession,
    *,
    user_id: int,
    challenge,
    now_utc: datetime,
) -> FriendChallengeJoinResult:
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
    if challenge.status == "EXPIRED":
        raise FriendChallengeExpiredError
    if challenge.status not in {
        DUEL_STATUS_PENDING,
        DUEL_STATUS_ACCEPTED,
        DUEL_STATUS_CREATOR_DONE,
        DUEL_STATUS_OPPONENT_DONE,
        DUEL_STATUS_LEGACY_ACTIVE,
    }:
        raise FriendChallengeCompletedError
    if challenge.creator_user_id == user_id:
        return FriendChallengeJoinResult(
            snapshot=_build_friend_challenge_snapshot(challenge),
            joined_now=False,
        )
    if challenge.opponent_user_id is None:
        challenge.opponent_user_id = user_id
        challenge.status = DUEL_STATUS_ACCEPTED
        challenge.expires_at = _friend_challenge_expires_at_accepted(now_utc=now_utc)
        challenge.updated_at = now_utc
        await emit_analytics_event(
            session,
            event_type="friend_challenge_joined",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=user_id,
            payload={
                "challenge_id": str(challenge.id),
                "creator_user_id": challenge.creator_user_id,
                "mode_code": challenge.mode_code,
                "total_rounds": challenge.total_rounds,
                "expires_at": challenge.expires_at.isoformat(),
                "series_id": str(challenge.series_id) if challenge.series_id is not None else None,
                "series_game_number": challenge.series_game_number,
                "series_best_of": challenge.series_best_of,
            },
        )
        await emit_analytics_event(
            session,
            event_type="duel_accepted",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=user_id,
            payload={
                "challenge_id": str(challenge.id),
                "challenge_type": challenge.challenge_type,
                "format": challenge.total_rounds,
            },
        )
        return FriendChallengeJoinResult(
            snapshot=_build_friend_challenge_snapshot(challenge),
            joined_now=True,
        )
    if challenge.opponent_user_id == user_id:
        return FriendChallengeJoinResult(
            snapshot=_build_friend_challenge_snapshot(challenge),
            joined_now=False,
        )
    raise FriendChallengeFullError
