from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.arena_attempts_repo import ArenaAttemptsRepo
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_ROLE_CHALLENGER,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_DUEL_STATUS_DRAFT,
    ARENA_DUEL_STATUS_EXPIRED,
)
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.sessions.errors import FriendChallengeAccessError

_ARENA_START_ROLES = frozenset(
    {
        ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
        ARENA_ATTEMPT_ROLE_CHALLENGER,
    }
)


async def _ensure_arena_attempt_can_start(
    session: AsyncSession,
    *,
    arena_attempt_id: UUID,
    user_id: int,
    mode_code: str,
    arena_round: int,
    forced_question_id: str | None,
    now_utc: datetime,
) -> str:
    context = await ArenaAttemptsRepo.get_start_context_for_update(session, arena_attempt_id)
    if context is None:
        raise FriendChallengeAccessError

    attempt = context.attempt
    if (
        attempt.user_id != user_id
        or attempt.role not in _ARENA_START_ROLES
        or attempt.score is not None
        or attempt.time_ms is not None
        or attempt.result is not None
        or attempt.completed_at is not None
    ):
        raise FriendChallengeAccessError

    duel = context.duel
    _ensure_arena_duel_allows_attempt_start(
        duel=duel,
        attempt=attempt,
        attempt_role=attempt.role,
        now_utc=now_utc,
    )
    expected_question_id = _arena_duel_question_id(duel.question_ids, arena_round)
    if duel.mode_code != mode_code or expected_question_id is None:
        raise FriendChallengeAccessError
    if forced_question_id is not None and forced_question_id != expected_question_id:
        raise FriendChallengeAccessError
    return expected_question_id


def _ensure_arena_duel_allows_attempt_start(
    *,
    duel: object,
    attempt: object,
    attempt_role: str,
    now_utc: datetime,
) -> None:
    expires_at = getattr(duel, "expires_at", None)
    if not isinstance(expires_at, datetime):
        raise FriendChallengeAccessError

    status = getattr(duel, "status", None)
    started_before_expiry = _arena_attempt_started_before_expiry(
        attempt=attempt,
        expires_at=expires_at,
    )
    if attempt_role == ARENA_ATTEMPT_ROLE_CREATOR_BASELINE:
        if status == ARENA_DUEL_STATUS_DRAFT and (expires_at > now_utc or started_before_expiry):
            return
        if status == ARENA_DUEL_STATUS_EXPIRED and expires_at <= now_utc and started_before_expiry:
            return
        raise FriendChallengeAccessError
    if attempt_role == ARENA_ATTEMPT_ROLE_CHALLENGER and (
        (status == ARENA_DUEL_STATUS_ACTIVE and (expires_at > now_utc or started_before_expiry))
        or (status == ARENA_DUEL_STATUS_EXPIRED and expires_at <= now_utc and started_before_expiry)
    ):
        return
    raise FriendChallengeAccessError


def _arena_attempt_started_before_expiry(*, attempt: object, expires_at: datetime) -> bool:
    created_at = getattr(attempt, "created_at", None)
    return isinstance(created_at, datetime) and created_at <= expires_at


def _arena_duel_question_id(question_ids: object, arena_round: int) -> str | None:
    if not isinstance(question_ids, list):
        return None
    if arena_round < 1 or arena_round > DUEL_QUESTION_COUNT:
        return None
    try:
        question_id = question_ids[arena_round - 1]
    except IndexError:
        return None
    if not isinstance(question_id, str) or not question_id:
        return None
    return question_id
