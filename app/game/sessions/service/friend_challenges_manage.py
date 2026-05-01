from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_BASELINE,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_SOURCE,
    arena_duel_expires_at,
)
from app.game.arena_duels.errors import ArenaDuelAccessError
from app.game.arena_duels.types import ArenaDuelSnapshot
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.duels.limits import DuelLimitService
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


async def publish_friend_challenge_to_arena(
    session: AsyncSession,
    *,
    user_id: int,
    friend_challenge_id: UUID,
    now_utc: datetime,
) -> ArenaDuelSnapshot:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, friend_challenge_id)
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
    if challenge.creator_user_id != user_id or challenge.status == DUEL_STATUS_EXPIRED:
        raise FriendChallengeAccessError
    if challenge.tournament_match_id is not None:
        raise FriendChallengeAccessError

    from app.db.repo.arena_duels_repo import ArenaDuelsRepo

    question_ids = _validate_arena_publish_question_ids(challenge.question_ids)
    if not _friend_creator_baseline_is_ready(challenge):
        raise FriendChallengeAccessError

    existing = await ArenaDuelsRepo.get_source_friend_duel_with_baseline_for_update(
        session,
        source_friend_challenge_id=challenge.id,
    )
    if existing is not None:
        return _build_arena_duel_snapshot(
            duel=existing.duel,
            baseline_attempt=existing.baseline_attempt,
        )

    access_type = str(challenge.access_type)
    DuelLimitService.assert_resolved_access_type(ARENA_SOURCE, access_type=access_type)
    baseline_time_ms = await QuizSessionsRepo.sum_completed_duration_ms_for_friend_challenge_user(
        session,
        friend_challenge_id=challenge.id,
        user_id=challenge.creator_user_id,
    )
    duel = await ArenaDuelsRepo.create_duel(
        session,
        duel=ArenaDuel(
            id=uuid4(),
            creator_user_id=challenge.creator_user_id,
            baseline_attempt_id=None,
            question_ids=list(question_ids),
            mode_code=challenge.mode_code,
            access_type=access_type,
            status=ARENA_DUEL_STATUS_ACTIVE,
            expires_at=arena_duel_expires_at(now_utc=now_utc),
            created_at=now_utc,
            updated_at=now_utc,
            source_friend_challenge_id=challenge.id,
        ),
    )
    baseline_attempt = await ArenaDuelsRepo.create_attempt(
        session,
        attempt=ArenaAttempt(
            id=uuid4(),
            arena_duel_id=duel.id,
            user_id=challenge.creator_user_id,
            role=ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
            access_type=access_type,
            score=int(challenge.creator_score),
            time_ms=baseline_time_ms,
            result=ARENA_ATTEMPT_RESULT_BASELINE,
            completed_at=challenge.creator_finished_at,
            created_at=now_utc,
        ),
    )
    duel.baseline_attempt_id = baseline_attempt.id
    await session.flush()
    return _build_arena_duel_snapshot(
        duel=duel,
        baseline_attempt=baseline_attempt,
    )


def _friend_creator_baseline_is_ready(challenge: FriendChallenge) -> bool:
    return (
        int(challenge.total_rounds) == DUEL_QUESTION_COUNT
        and int(challenge.creator_answered_round) >= DUEL_QUESTION_COUNT
        and challenge.creator_finished_at is not None
    )


def _validate_arena_publish_question_ids(question_ids: object) -> tuple[str, ...]:
    if not isinstance(question_ids, list):
        raise ArenaDuelAccessError
    validated = tuple(question_id for question_id in question_ids if isinstance(question_id, str))
    if len(validated) != DUEL_QUESTION_COUNT or any(not question_id for question_id in validated):
        raise ArenaDuelAccessError
    return validated


def _build_arena_duel_snapshot(
    *,
    duel: ArenaDuel,
    baseline_attempt: ArenaAttempt,
) -> ArenaDuelSnapshot:
    return ArenaDuelSnapshot(
        duel_id=duel.id,
        creator_user_id=duel.creator_user_id,
        mode_code=duel.mode_code,
        status=duel.status,
        question_ids=_validate_arena_publish_question_ids(duel.question_ids),
        baseline_attempt_id=baseline_attempt.id,
        baseline_score=baseline_attempt.score,
        baseline_time_ms=baseline_attempt.time_ms,
        expires_at=duel.expires_at,
        created_at=duel.created_at,
        updated_at=duel.updated_at,
    )
