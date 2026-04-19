from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.game.questions.types import QuizQuestion

from .levels import _is_persistent_adaptive_mode
from .progression import resolve_start_progression_state, select_level_weighted


async def _get_forced_question(
    session: AsyncSession,
    *,
    mode_code: str,
    local_date: date,
    forced_question_id: str | None,
) -> QuizQuestion | None:
    if forced_question_id is None:
        return None

    from app.game.sessions import service as service_module

    return await service_module.get_question_by_id(
        session,
        mode_code,
        question_id=forced_question_id,
        local_date_berlin=local_date,
    )


async def _resolve_start_progression_preferences(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    preferred_question_level: str | None,
    now_utc: datetime,
) -> tuple[str | None, int, tuple[str, ...] | None]:
    effective_preferred_level = preferred_question_level
    mix_step = 0
    allowed_levels: tuple[str, ...] | None = None
    if _is_persistent_adaptive_mode(mode_code=mode_code):
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
    return effective_preferred_level, mix_step, allowed_levels


async def _get_recent_question_ids_for_start(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
) -> list[str]:
    if source == "FRIEND_CHALLENGE":
        return []
    return await QuizAttemptsRepo.get_recent_question_ids_for_mode(
        session,
        user_id=user_id,
        mode_code=mode_code,
        limit=20,
    )


async def _select_question_for_start(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    idempotency_key: str,
    local_date: date,
    selection_seed_override: str | None,
    preferred_question_level: str | None,
    now_utc: datetime,
) -> QuizQuestion:
    (
        effective_preferred_level,
        mix_step,
        allowed_levels,
    ) = await _resolve_start_progression_preferences(
        session,
        user_id=user_id,
        mode_code=mode_code,
        preferred_question_level=preferred_question_level,
        now_utc=now_utc,
    )
    recent_question_ids = await _get_recent_question_ids_for_start(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source=source,
    )
    selection_seed = selection_seed_override or idempotency_key
    if _is_persistent_adaptive_mode(mode_code=mode_code) and effective_preferred_level is not None:
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


async def resolve_start_question(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    idempotency_key: str,
    local_date: date,
    selection_seed_override: str | None,
    preferred_question_level: str | None,
    forced_question_id: str | None,
    now_utc: datetime,
) -> QuizQuestion:
    question = await _get_forced_question(
        session,
        mode_code=mode_code,
        local_date=local_date,
        forced_question_id=forced_question_id,
    )
    if question is not None:
        return question
    return await _select_question_for_start(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source=source,
        idempotency_key=idempotency_key,
        local_date=local_date,
        selection_seed_override=selection_seed_override,
        preferred_question_level=preferred_question_level,
        now_utc=now_utc,
    )
