from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import ArenaDuelsRepo
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_ROLE_CHALLENGER,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_SOURCE,
)
from app.game.arena_duels.errors import (
    ArenaDuelAccessError,
    ArenaDuelAlreadyAttemptedError,
    ArenaDuelExpiredError,
    ArenaDuelNotFoundError,
    ArenaDuelOwnAttemptError,
)
from app.game.arena_duels.types import (
    ArenaActiveDuelSnapshot,
    ArenaChallengerStartResult,
    ArenaDuelSnapshot,
)
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.duels.limits import DuelLimitService
from app.game.sessions.service.sessions_start import start_session


async def accept_arena_duel(
    session: AsyncSession,
    *,
    duel_id: UUID,
    user_id: int,
    now_utc: datetime,
    duel_limit_checked: bool,
) -> ArenaChallengerStartResult:
    DuelLimitService.assert_start_gate(ARENA_SOURCE, duel_limit_checked=duel_limit_checked)

    context = await ArenaDuelsRepo.get_accept_context_for_update(
        session,
        duel_id=duel_id,
        user_id=user_id,
    )
    if context is None:
        raise ArenaDuelNotFoundError

    duel = context.duel
    _ensure_duel_can_be_accepted(
        duel=duel,
        user_id=user_id,
        existing_attempt=context.existing_attempt,
        now_utc=now_utc,
    )

    challenger_attempt = await ArenaDuelsRepo.create_attempt(
        session,
        attempt=ArenaAttempt(
            id=uuid4(),
            arena_duel_id=duel.id,
            user_id=user_id,
            role=ARENA_ATTEMPT_ROLE_CHALLENGER,
            score=None,
            time_ms=None,
            result=None,
            completed_at=None,
            created_at=now_utc,
        ),
    )
    start_result = await start_session(
        session,
        user_id=user_id,
        mode_code=duel.mode_code,
        source=ARENA_SOURCE,
        idempotency_key=f"arena:attempt:{challenger_attempt.id}:1",
        now_utc=now_utc,
        arena_attempt_id=challenger_attempt.id,
        arena_round=1,
        duel_limit_checked=True,
    )
    return ArenaChallengerStartResult(
        duel=_build_duel_snapshot(duel),
        challenger_attempt_id=challenger_attempt.id,
        start_result=start_result,
    )


async def get_arena_duel_accept_preview(
    session: AsyncSession,
    *,
    duel_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> ArenaActiveDuelSnapshot:
    context = await ArenaDuelsRepo.get_accept_context_for_update(
        session,
        duel_id=duel_id,
        user_id=user_id,
    )
    if context is None:
        raise ArenaDuelNotFoundError

    duel = context.duel
    _ensure_duel_can_be_accepted(
        duel=duel,
        user_id=user_id,
        existing_attempt=context.existing_attempt,
        now_utc=now_utc,
    )
    target_attempt, target_score, target_time_ms = await _get_current_best_attempt(
        session, duel_id=duel.id
    )

    return ArenaActiveDuelSnapshot(
        duel_id=duel.id,
        creator_user_id=target_attempt.user_id,
        mode_code=duel.mode_code,
        question_ids=_validate_question_ids(duel.question_ids),
        baseline_attempt_id=target_attempt.id,
        score=target_score,
        time_ms=target_time_ms,
        expires_at=duel.expires_at,
    )


def _ensure_duel_can_be_accepted(
    *,
    duel: ArenaDuel,
    user_id: int,
    existing_attempt: ArenaAttempt | None,
    now_utc: datetime,
) -> None:
    if duel.creator_user_id == user_id:
        raise ArenaDuelOwnAttemptError
    if existing_attempt is not None:
        raise ArenaDuelAlreadyAttemptedError
    if duel.status != ARENA_DUEL_STATUS_ACTIVE:
        raise ArenaDuelAccessError
    if duel.expires_at <= now_utc:
        raise ArenaDuelExpiredError
    if duel.baseline_attempt_id is None:
        raise ArenaDuelAccessError
    _validate_question_ids(duel.question_ids)


async def _get_current_best_attempt(
    session: AsyncSession, *, duel_id: UUID
) -> tuple[ArenaAttempt, int, int]:
    completed_attempts = await ArenaDuelsRepo.list_completed_attempts_for_duel(
        session,
        duel_id=duel_id,
    )
    if not completed_attempts:
        raise ArenaDuelAccessError
    best_attempt = completed_attempts[0]
    score = best_attempt.score
    time_ms = best_attempt.time_ms
    if score is None or time_ms is None:
        raise ArenaDuelAccessError
    return best_attempt, score, time_ms


def _build_duel_snapshot(duel: ArenaDuel) -> ArenaDuelSnapshot:
    return ArenaDuelSnapshot(
        duel_id=duel.id,
        creator_user_id=duel.creator_user_id,
        mode_code=duel.mode_code,
        status=duel.status,
        question_ids=_validate_question_ids(duel.question_ids),
        baseline_attempt_id=duel.baseline_attempt_id,
        baseline_score=None,
        baseline_time_ms=None,
        expires_at=duel.expires_at,
        created_at=duel.created_at,
        updated_at=duel.updated_at,
    )


def _validate_question_ids(question_ids: Sequence[object]) -> tuple[str, ...]:
    validated = tuple(question_id for question_id in question_ids if isinstance(question_id, str))
    if len(validated) != DUEL_QUESTION_COUNT or any(not question_id for question_id in validated):
        raise ArenaDuelAccessError
    return validated
