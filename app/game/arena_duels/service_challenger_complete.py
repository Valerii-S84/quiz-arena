from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import ArenaAttemptDuelContext, ArenaDuelsRepo
from app.game.arena_duels.analytics import ARENA_EVENT_ARENA_DUEL_COMPLETED
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_DRAW,
    ARENA_ATTEMPT_RESULT_LOSS,
    ARENA_ATTEMPT_RESULT_WIN,
    ARENA_ATTEMPT_ROLE_CHALLENGER,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_BEATEN_NOTIFICATION_TYPE,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_DUEL_STATUS_EXPIRED,
)
from app.game.arena_duels.errors import (
    ArenaDuelAccessError,
    ArenaDuelIncompleteError,
    ArenaDuelNotFoundError,
)
from app.game.arena_duels.scoring import decide_arena_scoring_outcome
from app.game.arena_duels.service_baseline_complete import complete_arena_creator_baseline_context
from app.game.arena_duels.service_common import (
    build_attempt_result_line,
    build_duel_snapshot,
    emit_arena_completion_events,
    get_previous_best_attempt,
    score_line,
    validate_question_ids,
)
from app.game.arena_duels.types import ArenaAttemptCompletionResult, ArenaBeatenNotification
from app.game.duels.constants import DUEL_QUESTION_COUNT


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
        snapshot = await complete_arena_creator_baseline_context(
            session,
            context=context,
            user_id=user_id,
            now_utc=now_utc,
        )
        return ArenaAttemptCompletionResult(
            duel=snapshot,
            completed_attempt=build_attempt_result_line(attempt),
        )
    if attempt.role == ARENA_ATTEMPT_ROLE_CHALLENGER:
        return await _complete_arena_challenger_context(
            session,
            context=context,
            now_utc=now_utc,
        )
    return None


async def _complete_arena_challenger_context(
    session: AsyncSession,
    *,
    context: ArenaAttemptDuelContext,
    now_utc: datetime,
) -> ArenaAttemptCompletionResult:
    attempt = context.attempt
    duel = context.duel
    _ensure_challenger_completion_access(attempt=attempt, duel=duel, now_utc=now_utc)
    if attempt.completed_at is not None:
        return ArenaAttemptCompletionResult(
            duel=build_duel_snapshot(duel=duel, baseline_attempt=None),
        )

    summary = await ArenaDuelsRepo.summarize_completed_attempt(session, attempt_id=attempt.id)
    if summary.completed_rounds != DUEL_QUESTION_COUNT:
        raise ArenaDuelIncompleteError

    previous_best = await get_previous_best_attempt(
        session,
        duel_id=duel.id,
        attempt_id=attempt.id,
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
        else _resolve_loss_or_draw(previous_best=previous_best, new_attempt=attempt)
    )
    duel.updated_at = now_utc
    await emit_arena_completion_events(
        session,
        event_type=ARENA_EVENT_ARENA_DUEL_COMPLETED,
        happened_at=now_utc,
        duel=duel,
        attempt=attempt,
        action="challenger",
    )
    return ArenaAttemptCompletionResult(
        duel=build_duel_snapshot(duel=duel, baseline_attempt=None),
        beaten_notification=notification,
        completed_attempt=build_attempt_result_line(attempt),
        opponent_attempt=build_attempt_result_line(previous_best),
    )


def _ensure_challenger_completion_access(
    *,
    attempt: ArenaAttempt,
    duel: ArenaDuel,
    now_utc: datetime,
) -> None:
    if (
        attempt.role != ARENA_ATTEMPT_ROLE_CHALLENGER
        or attempt.arena_duel_id != duel.id
        or duel.baseline_attempt_id is None
    ):
        raise ArenaDuelAccessError
    if duel.status == ARENA_DUEL_STATUS_ACTIVE:
        validate_question_ids(duel.question_ids)
        return
    if duel.status == ARENA_DUEL_STATUS_EXPIRED and duel.expires_at <= now_utc:
        if attempt.created_at <= duel.expires_at:
            validate_question_ids(duel.question_ids)
            return
    raise ArenaDuelAccessError


def _build_beaten_notification(
    *,
    duel: ArenaDuel,
    previous_best: ArenaAttempt,
    new_attempt: ArenaAttempt,
) -> ArenaBeatenNotification | None:
    previous_line = score_line(previous_best)
    new_line = score_line(new_attempt)
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


def _resolve_loss_or_draw(*, previous_best: ArenaAttempt, new_attempt: ArenaAttempt) -> str:
    outcome = decide_arena_scoring_outcome(
        baseline=score_line(previous_best),
        challenger=score_line(new_attempt),
    )
    if outcome.challenger_result == ARENA_ATTEMPT_RESULT_DRAW:
        return ARENA_ATTEMPT_RESULT_DRAW
    return ARENA_ATTEMPT_RESULT_LOSS
