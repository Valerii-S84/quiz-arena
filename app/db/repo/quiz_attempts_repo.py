from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_attempts import QuizAttempt


class QuizAttemptsRepo:
    @staticmethod
    async def get_by_idempotency_key(session: AsyncSession, idempotency_key: str) -> QuizAttempt | None:
        stmt = select(QuizAttempt).where(QuizAttempt.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, *, attempt: QuizAttempt) -> QuizAttempt:
        session.add(attempt)
        await session.flush()
        return attempt
