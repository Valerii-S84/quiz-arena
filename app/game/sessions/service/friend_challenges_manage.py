from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.game.arena_duels.types import ArenaDuelSnapshot
from app.game.friend_challenges.constants import (
    DUEL_STATUS_CANCELED,
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_EXPIRED,
    DUEL_STATUS_PENDING,
    DUEL_TYPE_OPEN,
    normalize_duel_status,
)
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_arena_publish import (
    ArenaPublishDependencies,
    publish_friend_challenge_to_arena_impl,
)
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
    if not _friend_challenge_can_be_canceled_by_creator(challenge):
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


async def publish_friend_challenge_to_arena(
    session: AsyncSession,
    *,
    user_id: int,
    friend_challenge_id: UUID,
    now_utc: datetime,
) -> ArenaDuelSnapshot:
    return await publish_friend_challenge_to_arena_impl(
        session=session,
        user_id=user_id,
        friend_challenge_id=friend_challenge_id,
        now_utc=now_utc,
        dependencies=ArenaPublishDependencies(
            friend_challenges_repo=FriendChallengesRepo,
            quiz_sessions_repo=QuizSessionsRepo,
            expire_friend_challenge_if_due=_expire_friend_challenge_if_due,
            emit_friend_challenge_expired_event=_emit_friend_challenge_expired_event,
        ),
    )


def _friend_challenge_can_be_canceled_by_creator(challenge: FriendChallenge) -> bool:
    if challenge.status == DUEL_STATUS_EXPIRED:
        return True
    return challenge.opponent_user_id is None and challenge.status in {
        DUEL_STATUS_PENDING,
        DUEL_STATUS_CREATOR_DONE,
    }
