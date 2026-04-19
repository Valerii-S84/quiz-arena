from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_sessions import QuizSession
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.energy.service import EnergyService
from app.game.modes.rules import is_zero_cost_source
from app.game.sessions.errors import EnergyInsufficientError
from app.game.sessions.types import StartSessionResult

from .question_loading import _build_start_result_from_created_session
from .sessions_start_question_selection import resolve_start_question
from .sessions_start_runtime_context import (
    ensure_friend_challenge_start_args,
    get_existing_or_daily_start_result,
)


async def _consume_start_energy(
    session: AsyncSession,
    *,
    user_id: int,
    source: str,
    idempotency_key: str,
    now_utc: datetime,
) -> tuple[int, int, int]:
    if is_zero_cost_source(source):
        return 0, 0, 0
    energy_result = await EnergyService.consume_quiz(
        session,
        user_id=user_id,
        idempotency_key=f"energy:{idempotency_key}",
        now_utc=now_utc,
    )
    if not energy_result.allowed:
        raise EnergyInsufficientError
    return energy_result.free_energy, energy_result.paid_energy, 1


async def _create_started_session(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    energy_cost_total: int,
    question_id: str,
    friend_challenge_id: UUID | None,
    friend_challenge_round: int | None,
    now_utc: datetime,
    local_date: date,
    idempotency_key: str,
) -> QuizSession:
    return await QuizSessionsRepo.create(
        session,
        quiz_session=QuizSession(
            id=uuid4(),
            user_id=user_id,
            mode_code=mode_code,
            source=source,
            status="STARTED",
            energy_cost_total=energy_cost_total,
            question_id=question_id,
            friend_challenge_id=friend_challenge_id,
            friend_challenge_round=friend_challenge_round,
            started_at=now_utc,
            local_date_berlin=local_date,
            idempotency_key=idempotency_key,
        ),
    )


async def start_session(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    idempotency_key: str,
    now_utc: datetime,
    selection_seed_override: str | None = None,
    preferred_question_level: str | None = None,
    forced_question_id: str | None = None,
    friend_challenge_id: UUID | None = None,
    friend_challenge_round: int | None = None,
    friend_challenge_total_rounds: int | None = None,
) -> StartSessionResult:
    ensure_friend_challenge_start_args(
        source=source,
        friend_challenge_id=friend_challenge_id,
        friend_challenge_round=friend_challenge_round,
    )
    local_date, prebuilt_result = await get_existing_or_daily_start_result(
        session,
        user_id=user_id,
        source=source,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )
    if prebuilt_result is not None:
        return prebuilt_result
    energy_free, energy_paid, energy_cost_total = await _consume_start_energy(
        session,
        user_id=user_id,
        source=source,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )
    question = await resolve_start_question(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source=source,
        idempotency_key=idempotency_key,
        local_date=local_date,
        selection_seed_override=selection_seed_override,
        preferred_question_level=preferred_question_level,
        forced_question_id=forced_question_id,
        now_utc=now_utc,
    )
    created = await _create_started_session(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source=source,
        energy_cost_total=energy_cost_total,
        question_id=question.question_id,
        friend_challenge_id=friend_challenge_id,
        friend_challenge_round=friend_challenge_round,
        now_utc=now_utc,
        local_date=local_date,
        idempotency_key=idempotency_key,
    )
    return _build_start_result_from_created_session(
        created=created,
        question=question,
        energy_free=energy_free,
        energy_paid=energy_paid,
        friend_challenge_total_rounds=friend_challenge_total_rounds,
    )
