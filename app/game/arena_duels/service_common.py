from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import ArenaActiveDuelRow, ArenaDuelsRepo
from app.game.arena_duels.analytics import build_arena_event_payload, emit_arena_analytics_event
from app.game.arena_duels.errors import ArenaDuelAccessError
from app.game.arena_duels.scoring import ArenaScoreLine
from app.game.arena_duels.types import (
    ArenaActiveDuelSnapshot,
    ArenaAttemptResultLine,
    ArenaDuelSnapshot,
)
from app.game.duels.constants import DUEL_QUESTION_COUNT


def validate_question_ids(question_ids: Sequence[object]) -> tuple[str, ...]:
    validated = tuple(question_id for question_id in question_ids if isinstance(question_id, str))
    if len(validated) != DUEL_QUESTION_COUNT or any(not question_id for question_id in validated):
        raise ArenaDuelAccessError
    return validated


def build_duel_snapshot(
    *,
    duel: ArenaDuel,
    baseline_attempt: ArenaAttempt | None,
) -> ArenaDuelSnapshot:
    return ArenaDuelSnapshot(
        duel_id=duel.id,
        creator_user_id=duel.creator_user_id,
        mode_code=duel.mode_code,
        status=duel.status,
        question_ids=validate_question_ids(duel.question_ids),
        baseline_attempt_id=duel.baseline_attempt_id,
        baseline_score=None if baseline_attempt is None else baseline_attempt.score,
        baseline_time_ms=None if baseline_attempt is None else baseline_attempt.time_ms,
        expires_at=duel.expires_at,
        created_at=duel.created_at,
        updated_at=duel.updated_at,
    )


def build_active_duel_snapshot(
    row: ArenaActiveDuelRow,
    *,
    current_best_attempt: ArenaAttempt,
) -> ArenaActiveDuelSnapshot | None:
    score = current_best_attempt.score
    time_ms = current_best_attempt.time_ms
    if score is None or time_ms is None:
        return None
    return ArenaActiveDuelSnapshot(
        duel_id=row.duel.id,
        creator_user_id=current_best_attempt.user_id,
        mode_code=row.duel.mode_code,
        question_ids=validate_question_ids(row.duel.question_ids),
        baseline_attempt_id=current_best_attempt.id,
        score=score,
        time_ms=time_ms,
        expires_at=row.duel.expires_at,
    )


def build_attempt_result_line(attempt: ArenaAttempt) -> ArenaAttemptResultLine:
    if attempt.score is None or attempt.time_ms is None:
        raise ArenaDuelAccessError
    return ArenaAttemptResultLine(
        user_id=attempt.user_id,
        score=attempt.score,
        time_ms=attempt.time_ms,
        result=attempt.result,
        attempt_id=attempt.id,
    )


def score_line(attempt: ArenaAttempt) -> ArenaScoreLine:
    if attempt.score is None or attempt.time_ms is None:
        raise ArenaDuelAccessError
    return ArenaScoreLine(
        user_id=attempt.user_id,
        score=attempt.score,
        time_ms=attempt.time_ms,
    )


async def get_previous_best_attempt(
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


async def get_current_best_attempt(
    session: AsyncSession,
    *,
    duel_id: UUID,
) -> ArenaAttempt | None:
    completed_attempts = await ArenaDuelsRepo.list_completed_attempts_for_duel(
        session,
        duel_id=duel_id,
    )
    if not completed_attempts:
        return None
    return completed_attempts[0]


async def emit_arena_completion_events(
    session: AsyncSession,
    *,
    event_type: str,
    happened_at: datetime,
    duel: ArenaDuel,
    attempt: ArenaAttempt,
    action: str,
) -> None:
    await emit_arena_analytics_event(
        session,
        event_type=event_type,
        happened_at=happened_at,
        user_id=attempt.user_id,
        payload=build_arena_event_payload(
            user_id=attempt.user_id,
            arena_duel_id=duel.id,
            attempt_id=attempt.id,
            action=action,
            access_type=attempt.access_type,
            result=attempt.result,
            score=attempt.score,
            time_ms=attempt.time_ms,
        ),
    )
