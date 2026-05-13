from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.daily_question_sets_repo import DailyQuestionSetsRepo

from .constants import DAILY_CHALLENGE_TOTAL_QUESTIONS
from .daily_question_set_selection import (
    DAILY_LEVEL_CHAIN,
    DAILY_POSITION_PREFERRED_LEVELS,
    build_daily_question_ids,
)
from .daily_question_set_selection import (
    daily_level_window_for_position as _daily_level_window_for_position,
)
from .daily_question_set_selection import (
    is_daily_level_allowed_for_position as _is_daily_level_allowed_for_position,
)


def daily_level_window_for_position(position: int) -> tuple[str, tuple[str, ...]]:
    return _daily_level_window_for_position(position)


def is_daily_level_allowed_for_position(*, position: int, level: str | None) -> bool:
    return _is_daily_level_allowed_for_position(position=position, level=level)


async def _build_daily_question_ids(
    session: AsyncSession,
    *,
    berlin_date: date,
) -> tuple[str, ...]:
    return await build_daily_question_ids(session, berlin_date=berlin_date)


async def _fallback_daily_question_id(
    session: AsyncSession,
    *,
    berlin_date: date,
) -> str:
    from app.game.sessions import service as service_module

    question = await service_module.select_question_for_mode(
        session,
        "DAILY_CHALLENGE",
        local_date_berlin=berlin_date,
        recent_question_ids=(),
        selection_seed=f"daily:fallback:{berlin_date.isoformat()}",
        preferred_level=DAILY_POSITION_PREFERRED_LEVELS[0],
        allowed_levels=DAILY_LEVEL_CHAIN,
    )
    return question.question_id


async def ensure_daily_question_set(
    session: AsyncSession,
    *,
    berlin_date: date,
) -> tuple[str, ...]:
    existing = await DailyQuestionSetsRepo.list_question_ids_for_date(
        session,
        berlin_date=berlin_date,
    )
    if len(existing) >= DAILY_CHALLENGE_TOTAL_QUESTIONS:
        return existing[:DAILY_CHALLENGE_TOTAL_QUESTIONS]

    generated = await _build_daily_question_ids(session, berlin_date=berlin_date)
    if generated:
        resolved = generated
        if len(generated) < DAILY_CHALLENGE_TOTAL_QUESTIONS:
            resolved = generated + (generated[0],) * (
                DAILY_CHALLENGE_TOTAL_QUESTIONS - len(generated)
            )
        await DailyQuestionSetsRepo.upsert_question_ids(
            session,
            berlin_date=berlin_date,
            question_ids=resolved[:DAILY_CHALLENGE_TOTAL_QUESTIONS],
        )
        existing = await DailyQuestionSetsRepo.list_question_ids_for_date(
            session,
            berlin_date=berlin_date,
        )
        if len(existing) >= DAILY_CHALLENGE_TOTAL_QUESTIONS:
            return existing[:DAILY_CHALLENGE_TOTAL_QUESTIONS]

    fallback_question_id = await _fallback_daily_question_id(session, berlin_date=berlin_date)
    fallback_set = (fallback_question_id,) * DAILY_CHALLENGE_TOTAL_QUESTIONS
    await DailyQuestionSetsRepo.upsert_question_ids(
        session,
        berlin_date=berlin_date,
        question_ids=fallback_set,
    )
    return fallback_set
