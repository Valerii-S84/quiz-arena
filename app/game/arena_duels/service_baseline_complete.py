from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import ArenaAttemptDuelContext, ArenaDuelsRepo
from app.game.arena_duels.analytics import (
    ARENA_EVENT_ARENA_DUEL_COMPLETED,
    ARENA_EVENT_ARENA_DUEL_PUBLISHED,
)
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_BASELINE,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_DUEL_STATUS_DRAFT,
    ARENA_DUEL_STATUS_EXPIRED,
    arena_duel_expires_at,
)
from app.game.arena_duels.errors import (
    ArenaDuelAccessError,
    ArenaDuelIncompleteError,
    ArenaDuelNotFoundError,
)
from app.game.arena_duels.service_common import (
    build_duel_snapshot,
    emit_arena_completion_events,
    validate_question_ids,
)
from app.game.arena_duels.types import ArenaDuelSnapshot
from app.game.duels.constants import DUEL_QUESTION_COUNT


async def complete_arena_creator_baseline(
    session: AsyncSession,
    *,
    attempt_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> ArenaDuelSnapshot:
    context = await ArenaDuelsRepo.get_attempt_duel_for_update(session, attempt_id=attempt_id)
    if context is None:
        raise ArenaDuelNotFoundError
    return await complete_arena_creator_baseline_context(
        session,
        context=context,
        user_id=user_id,
        now_utc=now_utc,
    )


async def complete_arena_creator_baseline_if_applicable(
    session: AsyncSession,
    *,
    attempt_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> ArenaDuelSnapshot | None:
    context = await ArenaDuelsRepo.get_attempt_duel_for_update(session, attempt_id=attempt_id)
    if context is None:
        raise ArenaDuelNotFoundError
    attempt = context.attempt
    if attempt.user_id != user_id:
        raise ArenaDuelAccessError
    if attempt.role != ARENA_ATTEMPT_ROLE_CREATOR_BASELINE:
        return None
    return await complete_arena_creator_baseline_context(
        session,
        context=context,
        user_id=user_id,
        now_utc=now_utc,
    )


async def complete_arena_creator_baseline_context(
    session: AsyncSession,
    *,
    context: ArenaAttemptDuelContext,
    user_id: int,
    now_utc: datetime,
) -> ArenaDuelSnapshot:
    attempt = context.attempt
    duel = context.duel
    _ensure_creator_baseline_access(attempt=attempt, duel=duel, user_id=user_id)
    if attempt.completed_at is not None:
        return _completed_baseline_snapshot(attempt=attempt, duel=duel)
    if not _creator_baseline_status_allows_completion(
        attempt=attempt,
        duel=duel,
        now_utc=now_utc,
    ):
        raise ArenaDuelAccessError

    validate_question_ids(duel.question_ids)
    summary = await ArenaDuelsRepo.summarize_completed_attempt(session, attempt_id=attempt.id)
    if summary.completed_rounds != DUEL_QUESTION_COUNT:
        raise ArenaDuelIncompleteError

    attempt.score = summary.score
    attempt.time_ms = summary.time_ms
    attempt.result = ARENA_ATTEMPT_RESULT_BASELINE
    attempt.completed_at = now_utc
    duel.baseline_attempt_id = attempt.id
    duel.status = ARENA_DUEL_STATUS_ACTIVE
    duel.expires_at = arena_duel_expires_at(now_utc=now_utc)
    duel.updated_at = now_utc

    await _emit_baseline_completed(session, duel=duel, attempt=attempt, now_utc=now_utc)
    return build_duel_snapshot(duel=duel, baseline_attempt=attempt)


def _completed_baseline_snapshot(*, attempt: ArenaAttempt, duel: ArenaDuel) -> ArenaDuelSnapshot:
    if duel.status == ARENA_DUEL_STATUS_ACTIVE and duel.baseline_attempt_id == attempt.id:
        return build_duel_snapshot(duel=duel, baseline_attempt=attempt)
    raise ArenaDuelAccessError


async def _emit_baseline_completed(
    session: AsyncSession,
    *,
    duel: ArenaDuel,
    attempt: ArenaAttempt,
    now_utc: datetime,
) -> None:
    for event_type in (ARENA_EVENT_ARENA_DUEL_COMPLETED, ARENA_EVENT_ARENA_DUEL_PUBLISHED):
        await emit_arena_completion_events(
            session,
            event_type=event_type,
            happened_at=now_utc,
            duel=duel,
            attempt=attempt,
            action="creator_baseline",
        )


def _ensure_creator_baseline_access(
    *,
    attempt: ArenaAttempt,
    duel: ArenaDuel,
    user_id: int,
) -> None:
    if (
        attempt.user_id != user_id
        or duel.creator_user_id != user_id
        or attempt.arena_duel_id != duel.id
        or attempt.role != ARENA_ATTEMPT_ROLE_CREATOR_BASELINE
    ):
        raise ArenaDuelAccessError


def _creator_baseline_status_allows_completion(
    *,
    attempt: ArenaAttempt,
    duel: ArenaDuel,
    now_utc: datetime,
) -> bool:
    if duel.baseline_attempt_id is not None:
        return False
    if duel.status == ARENA_DUEL_STATUS_DRAFT:
        return True
    return (
        duel.status == ARENA_DUEL_STATUS_EXPIRED
        and duel.expires_at <= now_utc
        and attempt.created_at <= duel.expires_at
    )
