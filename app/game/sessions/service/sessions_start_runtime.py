from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_sessions import QuizSession
from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.energy.service import EnergyService
from app.game.modes.rules import is_zero_cost_source
from app.game.questions.types import QuizQuestion
from app.game.sessions.errors import EnergyInsufficientError, FriendChallengeAccessError

from .levels import _clamp_level_for_mode
from .progression_config import get_allowed_levels


async def _consume_start_energy_if_needed(
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
        ledger_idempotency_prechecked=True,
    )
    if not energy_result.allowed:
        raise EnergyInsufficientError
    return energy_result.free_energy, energy_result.paid_energy, 1


async def _resolve_start_question(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    local_date: date,
    selection_seed_override: str | None,
    idempotency_key: str,
    now_utc: datetime,
    forced_question_id: str | None,
    preferred_question_level: str | None,
    preferred_question_mix_step: int | None,
    recent_question_ids_override: tuple[str, ...] | None,
    resolve_start_progression_state,
    select_level_weighted,
    is_persistent_adaptive_mode,
) -> QuizQuestion:
    question = None
    if forced_question_id is not None:
        from app.game.sessions import service as service_module

        question = await service_module.get_question_by_id(
            session,
            mode_code,
            question_id=forced_question_id,
            local_date_berlin=local_date,
        )
    if source == "ARENA_DUEL" and question is None:
        raise FriendChallengeAccessError
    if question is not None:
        return question

    effective_preferred_level = preferred_question_level
    allowed_levels: tuple[str, ...] | None = None
    mix_step = 0
    if is_persistent_adaptive_mode(mode_code=mode_code):
        if effective_preferred_level is not None and preferred_question_mix_step is not None:
            effective_preferred_level = _clamp_level_for_mode(
                mode_code=mode_code,
                level=effective_preferred_level,
            )
            if effective_preferred_level is None:
                effective_preferred_level = preferred_question_level
            assert effective_preferred_level is not None
            mix_step = max(0, int(preferred_question_mix_step))
            allowed_levels = get_allowed_levels(effective_preferred_level, mix_step)
        else:
            (
                effective_preferred_level,
                mix_step,
                allowed_levels,
            ) = await resolve_start_progression_state(
                session,
                user_id=user_id,
                mode_code=mode_code,
                preferred_level_override=effective_preferred_level,
                now_utc=now_utc,
            )

    recent_question_ids: list[str] = list(recent_question_ids_override or ())
    if source != "FRIEND_CHALLENGE" and recent_question_ids_override is None:
        recent_question_ids = await QuizAttemptsRepo.get_recent_question_ids_for_mode(
            session,
            user_id=user_id,
            mode_code=mode_code,
            limit=20,
        )
    selection_seed = selection_seed_override or idempotency_key
    if is_persistent_adaptive_mode(mode_code=mode_code) and effective_preferred_level is not None:
        effective_preferred_level = select_level_weighted(
            effective_preferred_level,
            mix_step,
            selection_seed=selection_seed,
        )

    from app.game.sessions import service as service_module

    return await service_module.select_question_for_mode(
        session,
        mode_code,
        local_date_berlin=local_date,
        recent_question_ids=recent_question_ids,
        selection_seed=selection_seed,
        preferred_level=effective_preferred_level,
        allowed_levels=allowed_levels,
    )


async def _create_started_session(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    question: QuizQuestion,
    energy_cost_total: int,
    now_utc: datetime,
    local_date: date,
    idempotency_key: str,
    friend_challenge_id: UUID | None,
    friend_challenge_round: int | None,
    arena_attempt_id: UUID | None,
    arena_round: int | None,
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
            question_id=question.question_id,
            friend_challenge_id=friend_challenge_id,
            friend_challenge_round=friend_challenge_round,
            arena_attempt_id=arena_attempt_id,
            arena_round=arena_round,
            started_at=now_utc,
            local_date_berlin=local_date,
            idempotency_key=idempotency_key,
        ),
    )
