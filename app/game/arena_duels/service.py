from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import ArenaActiveDuelRow, ArenaAttemptDuelContext, ArenaDuelsRepo
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_BASELINE,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DEFAULT_ACTIVE_LIST_LIMIT,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_DUEL_STATUS_DRAFT,
    ARENA_SOURCE,
    arena_duel_expires_at,
)
from app.game.arena_duels.errors import (
    ArenaDuelAccessError,
    ArenaDuelIncompleteError,
    ArenaDuelNotFoundError,
)
from app.game.arena_duels.types import (
    ArenaActiveDuelSnapshot,
    ArenaBaselineStartResult,
    ArenaDuelSnapshot,
)
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.duels.limits import DuelLimitService
from app.game.sessions.service.friend_challenges_question_plan import select_duel_question_ids
from app.game.sessions.service.sessions_start import start_session


async def create_arena_duel_baseline(
    session: AsyncSession,
    *,
    creator_user_id: int,
    mode_code: str,
    now_utc: datetime,
    duel_limit_checked: bool,
) -> ArenaBaselineStartResult:
    DuelLimitService.assert_start_gate(ARENA_SOURCE, duel_limit_checked=duel_limit_checked)

    duel_id = uuid4()
    question_ids = await select_duel_question_ids(
        session,
        mode_code=mode_code,
        total_rounds=DUEL_QUESTION_COUNT,
        now_utc=now_utc,
        challenge_seed=str(duel_id),
    )
    validated_question_ids = _validate_question_ids(question_ids)

    duel = await ArenaDuelsRepo.create_duel(
        session,
        duel=ArenaDuel(
            id=duel_id,
            creator_user_id=creator_user_id,
            baseline_attempt_id=None,
            question_ids=list(validated_question_ids),
            mode_code=mode_code,
            status=ARENA_DUEL_STATUS_DRAFT,
            expires_at=arena_duel_expires_at(now_utc=now_utc),
            created_at=now_utc,
            updated_at=now_utc,
            source_friend_challenge_id=None,
        ),
    )

    baseline_attempt = await ArenaDuelsRepo.create_attempt(
        session,
        attempt=ArenaAttempt(
            id=uuid4(),
            arena_duel_id=duel.id,
            user_id=creator_user_id,
            role=ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
            score=None,
            time_ms=None,
            result=None,
            completed_at=None,
            created_at=now_utc,
        ),
    )
    start_result = await start_session(
        session,
        user_id=creator_user_id,
        mode_code=mode_code,
        source=ARENA_SOURCE,
        idempotency_key=f"arena:baseline:{baseline_attempt.id}:1",
        now_utc=now_utc,
        arena_attempt_id=baseline_attempt.id,
        arena_round=1,
        duel_limit_checked=True,
    )
    return ArenaBaselineStartResult(
        duel=_build_duel_snapshot(duel=duel, baseline_attempt=None),
        baseline_attempt_id=baseline_attempt.id,
        start_result=start_result,
    )


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

    return await _complete_arena_creator_baseline_context(
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
    return await _complete_arena_creator_baseline_context(
        session,
        context=context,
        user_id=user_id,
        now_utc=now_utc,
    )


async def _complete_arena_creator_baseline_context(
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
        if duel.status == ARENA_DUEL_STATUS_ACTIVE and duel.baseline_attempt_id == attempt.id:
            return _build_duel_snapshot(duel=duel, baseline_attempt=attempt)
        raise ArenaDuelAccessError
    if duel.status != ARENA_DUEL_STATUS_DRAFT or duel.baseline_attempt_id is not None:
        raise ArenaDuelAccessError

    _validate_question_ids(duel.question_ids)
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

    return _build_duel_snapshot(duel=duel, baseline_attempt=attempt)


async def list_active_arena_duels(
    session: AsyncSession,
    *,
    now_utc: datetime,
    limit: int = ARENA_DEFAULT_ACTIVE_LIST_LIMIT,
) -> tuple[ArenaActiveDuelSnapshot, ...]:
    rows = await ArenaDuelsRepo.list_active_with_baseline(
        session,
        now_utc=now_utc,
        limit=limit,
    )
    snapshots: list[ArenaActiveDuelSnapshot] = []
    for row in rows:
        snapshot = _build_active_duel_snapshot(row)
        if snapshot is not None:
            snapshots.append(snapshot)
    return tuple(snapshots)


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


def _build_duel_snapshot(
    *,
    duel: ArenaDuel,
    baseline_attempt: ArenaAttempt | None,
) -> ArenaDuelSnapshot:
    return ArenaDuelSnapshot(
        duel_id=duel.id,
        creator_user_id=duel.creator_user_id,
        mode_code=duel.mode_code,
        status=duel.status,
        question_ids=_validate_question_ids(duel.question_ids),
        baseline_attempt_id=duel.baseline_attempt_id,
        baseline_score=None if baseline_attempt is None else baseline_attempt.score,
        baseline_time_ms=None if baseline_attempt is None else baseline_attempt.time_ms,
        expires_at=duel.expires_at,
        created_at=duel.created_at,
        updated_at=duel.updated_at,
    )


def _build_active_duel_snapshot(row: ArenaActiveDuelRow) -> ArenaActiveDuelSnapshot | None:
    score = row.baseline_attempt.score
    time_ms = row.baseline_attempt.time_ms
    baseline_attempt_id = row.duel.baseline_attempt_id
    if score is None or time_ms is None or baseline_attempt_id is None:
        return None
    return ArenaActiveDuelSnapshot(
        duel_id=row.duel.id,
        creator_user_id=row.duel.creator_user_id,
        mode_code=row.duel.mode_code,
        question_ids=_validate_question_ids(row.duel.question_ids),
        baseline_attempt_id=baseline_attempt_id,
        score=score,
        time_ms=time_ms,
        expires_at=row.duel.expires_at,
    )


def _validate_question_ids(question_ids: Sequence[object]) -> tuple[str, ...]:
    validated = tuple(question_id for question_id in question_ids if isinstance(question_id, str))
    if len(validated) != DUEL_QUESTION_COUNT or any(not question_id for question_id in validated):
        raise ArenaDuelAccessError
    return validated
