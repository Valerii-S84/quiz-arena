from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession


async def recent_attempt_results(
    db: AsyncSession,
    *,
    user_id: int,
    mode: str,
    limit: int,
) -> list[bool]:
    stmt = (
        select(QuizAttempt.is_correct)
        .join(QuizSession, QuizAttempt.session_id == QuizSession.id)
        .where(
            QuizAttempt.user_id == user_id,
            QuizSession.mode_code == mode,
        )
        .order_by(QuizAttempt.answered_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [bool(value) for value in result.scalars().all()]


__all__ = ["recent_attempt_results"]
