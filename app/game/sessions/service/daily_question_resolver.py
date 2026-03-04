from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.questions.types import QuizQuestion
from app.game.sessions.errors import DailyChallengeAlreadyPlayedError

from .daily_question_sets import (
    daily_level_window_for_position,
    ensure_daily_question_set,
    is_daily_level_allowed_for_position,
)


async def _select_daily_fallback_question(
    session: AsyncSession,
    *,
    berlin_date: date,
    position: int,
) -> QuizQuestion:
    preferred_level, allowed_levels = daily_level_window_for_position(position)
    from app.game.sessions import service as service_module

    return await service_module.select_question_for_mode(
        session,
        "DAILY_CHALLENGE",
        local_date_berlin=berlin_date,
        recent_question_ids=(),
        selection_seed=f"daily:resolver:fallback:{berlin_date.isoformat()}:{position}",
        preferred_level=preferred_level,
        allowed_levels=allowed_levels,
    )


async def resolve_daily_question_for_position(
    session: AsyncSession,
    *,
    berlin_date: date,
    position: int,
) -> tuple[str, QuizQuestion]:
    question_ids = await ensure_daily_question_set(session, berlin_date=berlin_date)
    if not question_ids:
        raise DailyChallengeAlreadyPlayedError

    from app.game.sessions import service as service_module

    index = max(0, min(len(question_ids) - 1, position - 1))
    question_id = question_ids[index]
    question = await service_module.get_question_by_id(
        session,
        "DAILY_CHALLENGE",
        question_id=question_id,
        local_date_berlin=berlin_date,
    )
    if question is not None and is_daily_level_allowed_for_position(
        position=position,
        level=question.level,
    ):
        return question_id, question

    fallback_question = await _select_daily_fallback_question(
        session,
        berlin_date=berlin_date,
        position=position,
    )
    return fallback_question.question_id, fallback_question
