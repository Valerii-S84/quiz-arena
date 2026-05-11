from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.game.arena_duels.constants import ARENA_DUEL_STATUS_ACTIVE, ARENA_SOURCE
from app.game.arena_duels.types import ArenaDuelSnapshot
from app.game.duels.limits import DuelLimitService
from app.game.friend_challenges.constants import normalize_duel_status
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError

from .friend_challenges_arena_publish_events import (
    EmitExpiredEvent,
    ExpireFriendChallenge,
    expire_friend_challenge_for_arena_publish,
)
from .friend_challenges_arena_publish_models import (
    build_arena_duel_snapshot,
    build_arena_publish_baseline_attempt,
    build_arena_publish_duel,
    validate_arena_publish_question_ids,
)
from .friend_challenges_arena_publish_rules import (
    ensure_friend_challenge_can_publish_to_arena,
    ensure_friend_creator_baseline_publishable,
)


@dataclass(frozen=True)
class ArenaPublishDependencies:
    friend_challenges_repo: Any
    quiz_sessions_repo: Any
    expire_friend_challenge_if_due: ExpireFriendChallenge
    emit_friend_challenge_expired_event: EmitExpiredEvent


async def publish_friend_challenge_to_arena_impl(
    session: AsyncSession,
    *,
    user_id: int,
    friend_challenge_id: UUID,
    now_utc: datetime,
    dependencies: ArenaPublishDependencies,
) -> ArenaDuelSnapshot:
    from app.db.repo.arena_duels_repo import ArenaDuelsRepo

    challenge = await _load_friend_challenge_for_arena_publish(
        session,
        user_id=user_id,
        friend_challenge_id=friend_challenge_id,
        now_utc=now_utc,
        friend_challenges_repo=dependencies.friend_challenges_repo,
        expire_friend_challenge_if_due=dependencies.expire_friend_challenge_if_due,
        emit_friend_challenge_expired_event=dependencies.emit_friend_challenge_expired_event,
    )
    ensure_friend_creator_baseline_publishable(challenge)
    question_ids = validate_arena_publish_question_ids(challenge.question_ids)
    existing_snapshot = await _get_existing_arena_publish_snapshot(
        session,
        challenge=challenge,
        now_utc=now_utc,
        arena_duels_repo=ArenaDuelsRepo,
    )
    if existing_snapshot is not None:
        return existing_snapshot

    return await _create_arena_publish_from_friend_challenge(
        session,
        challenge=challenge,
        question_ids=question_ids,
        now_utc=now_utc,
        arena_duels_repo=ArenaDuelsRepo,
        quiz_sessions_repo=dependencies.quiz_sessions_repo,
    )


async def _load_friend_challenge_for_arena_publish(
    session: AsyncSession,
    *,
    user_id: int,
    friend_challenge_id: UUID,
    now_utc: datetime,
    friend_challenges_repo: Any,
    expire_friend_challenge_if_due: ExpireFriendChallenge,
    emit_friend_challenge_expired_event: EmitExpiredEvent,
) -> FriendChallenge:
    challenge = await friend_challenges_repo.get_by_id_for_update(session, friend_challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError
    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=challenge.opponent_user_id is not None,
    )
    await expire_friend_challenge_for_arena_publish(
        session,
        challenge=challenge,
        now_utc=now_utc,
        expire_friend_challenge_if_due=expire_friend_challenge_if_due,
        emit_friend_challenge_expired_event=emit_friend_challenge_expired_event,
    )
    ensure_friend_challenge_can_publish_to_arena(challenge=challenge, user_id=user_id)
    return challenge


async def _get_existing_arena_publish_snapshot(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    now_utc: datetime,
    arena_duels_repo: Any,
) -> ArenaDuelSnapshot | None:
    existing = await arena_duels_repo.get_source_friend_duel_with_baseline_for_update(
        session,
        source_friend_challenge_id=challenge.id,
    )
    if existing is None:
        return None
    if existing.duel.status != ARENA_DUEL_STATUS_ACTIVE or existing.duel.expires_at <= now_utc:
        raise FriendChallengeAccessError
    return build_arena_duel_snapshot(
        duel=existing.duel,
        baseline_attempt=existing.baseline_attempt,
    )


async def _create_arena_publish_from_friend_challenge(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    question_ids: tuple[str, ...],
    now_utc: datetime,
    arena_duels_repo: Any,
    quiz_sessions_repo: Any,
) -> ArenaDuelSnapshot:
    access_type = str(challenge.access_type)
    DuelLimitService.assert_resolved_access_type(ARENA_SOURCE, access_type=access_type)
    baseline_time_ms = await quiz_sessions_repo.sum_completed_duration_ms_for_friend_challenge_user(
        session,
        friend_challenge_id=challenge.id,
        user_id=challenge.creator_user_id,
    )
    duel = await arena_duels_repo.create_duel(
        session,
        duel=build_arena_publish_duel(
            challenge=challenge,
            question_ids=question_ids,
            access_type=access_type,
            now_utc=now_utc,
        ),
    )
    baseline_attempt = await arena_duels_repo.create_attempt(
        session,
        attempt=build_arena_publish_baseline_attempt(
            duel=duel,
            challenge=challenge,
            access_type=access_type,
            baseline_time_ms=baseline_time_ms,
            now_utc=now_utc,
        ),
    )
    duel.baseline_attempt_id = baseline_attempt.id
    await session.flush()
    return build_arena_duel_snapshot(
        duel=duel,
        baseline_attempt=baseline_attempt,
    )
