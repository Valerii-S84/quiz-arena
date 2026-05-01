from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import ArenaActiveDuelRow, ArenaAttemptDuelContext, ArenaDuelsRepo
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_BASELINE,
    ARENA_ATTEMPT_RESULT_DRAW,
    ARENA_ATTEMPT_RESULT_LOSS,
    ARENA_ATTEMPT_RESULT_WIN,
    ARENA_ATTEMPT_ROLE_CHALLENGER,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_BEATEN_NOTIFICATION_TYPE,
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
from app.game.arena_duels.scoring import ArenaScoreLine, decide_arena_scoring_outcome
from app.game.arena_duels.types import (
    ArenaActiveDuelSnapshot,
    ArenaAttemptCompletionResult,
    ArenaAttemptResultLine,
    ArenaBaselineStartResult,
    ArenaBeatenNotification,
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


async def complete_arena_attempt_if_applicable(
    session: AsyncSession,
    *,
    attempt_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> ArenaAttemptCompletionResult | None:
    context = await ArenaDuelsRepo.get_attempt_duel_for_update(session, attempt_id=attempt_id)
    if context is None:
        raise ArenaDuelNotFoundError

    attempt = context.attempt
    if attempt.user_id != user_id:
        raise ArenaDuelAccessError
    if attempt.role == ARENA_ATTEMPT_ROLE_CREATOR_BASELINE:
        snapshot = await _complete_arena_creator_baseline_context(
            session,
            context=context,
            user_id=user_id,
            now_utc=now_utc,
        )
        return ArenaAttemptCompletionResult(
            duel=snapshot,
            completed_attempt=_build_attempt_result_line(attempt),
        )
    if attempt.role == ARENA_ATTEMPT_ROLE_CHALLENGER:
        return await _complete_arena_challenger_context(
            session,
            context=context,
            now_utc=now_utc,
        )
    return None


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


async def _complete_arena_challenger_context(
    session: AsyncSession,
    *,
    context: ArenaAttemptDuelContext,
    now_utc: datetime,
) -> ArenaAttemptCompletionResult:
    attempt = context.attempt
    duel = context.duel
    _ensure_challenger_completion_access(attempt=attempt, duel=duel)
    if attempt.completed_at is not None:
        # The original comparison opponent is not persisted. Suppress replay
        # rendering instead of pairing the stored result with a changed leaderboard.
        return ArenaAttemptCompletionResult(
            duel=_build_duel_snapshot(duel=duel, baseline_attempt=None),
        )

    summary = await ArenaDuelsRepo.summarize_completed_attempt(session, attempt_id=attempt.id)
    if summary.completed_rounds != DUEL_QUESTION_COUNT:
        raise ArenaDuelIncompleteError

    previous_best = await _get_previous_best_attempt(
        session, duel_id=duel.id, attempt_id=attempt.id
    )
    attempt.score = summary.score
    attempt.time_ms = summary.time_ms
    attempt.completed_at = now_utc

    notification = _build_beaten_notification(
        duel=duel,
        previous_best=previous_best,
        new_attempt=attempt,
    )
    attempt.result = (
        ARENA_ATTEMPT_RESULT_WIN
        if notification is not None
        else _resolve_loss_or_draw(
            previous_best=previous_best,
            new_attempt=attempt,
        )
    )
    duel.updated_at = now_utc

    return ArenaAttemptCompletionResult(
        duel=_build_duel_snapshot(duel=duel, baseline_attempt=None),
        beaten_notification=notification,
        completed_attempt=_build_attempt_result_line(attempt),
        opponent_attempt=_build_attempt_result_line(previous_best),
    )


def _build_attempt_result_line(attempt: ArenaAttempt) -> ArenaAttemptResultLine:
    if attempt.score is None or attempt.time_ms is None:
        raise ArenaDuelAccessError
    return ArenaAttemptResultLine(
        user_id=attempt.user_id,
        score=attempt.score,
        time_ms=attempt.time_ms,
        result=attempt.result,
    )


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


def _ensure_challenger_completion_access(
    *,
    attempt: ArenaAttempt,
    duel: ArenaDuel,
) -> None:
    if (
        attempt.role != ARENA_ATTEMPT_ROLE_CHALLENGER
        or attempt.arena_duel_id != duel.id
        or duel.status != ARENA_DUEL_STATUS_ACTIVE
        or duel.baseline_attempt_id is None
    ):
        raise ArenaDuelAccessError
    _validate_question_ids(duel.question_ids)


async def _get_previous_best_attempt(
    session: AsyncSession,
    *,
    duel_id: UUID,
    attempt_id: UUID,
) -> ArenaAttempt:
    completed_attempts = await ArenaDuelsRepo.list_completed_attempts_for_duel(
        session,
        duel_id=duel_id,
        exclude_attempt_id=attempt_id,
    )
    if not completed_attempts:
        raise ArenaDuelAccessError
    return completed_attempts[0]


def _build_beaten_notification(
    *,
    duel: ArenaDuel,
    previous_best: ArenaAttempt,
    new_attempt: ArenaAttempt,
) -> ArenaBeatenNotification | None:
    previous_line = _score_line(previous_best)
    new_line = _score_line(new_attempt)
    outcome = decide_arena_scoring_outcome(baseline=previous_line, challenger=new_line)
    if not outcome.challenger_won:
        return None
    return ArenaBeatenNotification(
        arena_duel_id=duel.id,
        previous_best_attempt_id=previous_best.id,
        previous_best_user_id=previous_best.user_id,
        previous_best_score=previous_line.score,
        previous_best_time_ms=previous_line.time_ms,
        new_best_attempt_id=new_attempt.id,
        new_best_user_id=new_attempt.user_id,
        new_best_score=new_line.score,
        new_best_time_ms=new_line.time_ms,
        notification_type=ARENA_BEATEN_NOTIFICATION_TYPE,
    )


def _resolve_loss_or_draw(
    *,
    previous_best: ArenaAttempt,
    new_attempt: ArenaAttempt,
) -> str:
    outcome = decide_arena_scoring_outcome(
        baseline=_score_line(previous_best),
        challenger=_score_line(new_attempt),
    )
    if outcome.challenger_result == ARENA_ATTEMPT_RESULT_DRAW:
        return ARENA_ATTEMPT_RESULT_DRAW
    return ARENA_ATTEMPT_RESULT_LOSS


def _score_line(attempt: ArenaAttempt) -> ArenaScoreLine:
    if attempt.score is None or attempt.time_ms is None:
        raise ArenaDuelAccessError
    return ArenaScoreLine(
        user_id=attempt.user_id,
        score=attempt.score,
        time_ms=attempt.time_ms,
    )


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
