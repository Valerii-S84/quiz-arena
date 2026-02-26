from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.questions.types import QuizQuestion
from app.game.sessions.errors import DailyChallengeAlreadyPlayedError

from .daily_question_sets import ensure_daily_question_set


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
    if question is not None:
        return question_id, question

    fallback_question = await service_module.get_question_for_mode(
        session,
        "DAILY_CHALLENGE",
        local_date_berlin=berlin_date,
    )
    return fallback_question.question_id, fallback_question
