from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.questions.types import QuizQuestion


async def load_forced_question(
    session: AsyncSession,
    *,
    mode_code: str,
    forced_question_id: str | None,
    local_date_berlin: date,
) -> QuizQuestion | None:
    if forced_question_id is None:
        return None
    from app.game.sessions import service as service_module

    return await service_module.get_question_by_id(
        session,
        mode_code,
        question_id=forced_question_id,
        local_date_berlin=local_date_berlin,
    )
