from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_sessions import QuizSession


class QuizSessionsRepo:
    @staticmethod
    async def get_by_id(session: AsyncSession, session_id: UUID) -> QuizSession | None:
        return await session.get(QuizSession, session_id)

    @staticmethod
    async def get_by_id_for_update(session: AsyncSession, session_id: UUID) -> QuizSession | None:
        stmt = select(QuizSession).where(QuizSession.id == session_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_idempotency_key(session: AsyncSession, idempotency_key: str) -> QuizSession | None:
        stmt = select(QuizSession).where(QuizSession.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_friend_challenge_round_user(
        session: AsyncSession,
        *,
        friend_challenge_id: UUID,
        friend_challenge_round: int,
        user_id: int,
    ) -> QuizSession | None:
        stmt = select(QuizSession).where(
            QuizSession.friend_challenge_id == friend_challenge_id,
            QuizSession.friend_challenge_round == friend_challenge_round,
            QuizSession.user_id == user_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_friend_challenge_round_any_user(
        session: AsyncSession,
        *,
        friend_challenge_id: UUID,
        friend_challenge_round: int,
    ) -> QuizSession | None:
        stmt = (
            select(QuizSession)
            .where(
                QuizSession.friend_challenge_id == friend_challenge_id,
                QuizSession.friend_challenge_round == friend_challenge_round,
            )
            .order_by(QuizSession.started_at.asc(), QuizSession.id.asc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_friend_challenge_question_ids_before_round(
        session: AsyncSession,
        *,
        friend_challenge_id: UUID,
        before_round: int,
    ) -> list[str]:
        stmt = (
            select(QuizSession.question_id)
            .where(
                QuizSession.friend_challenge_id == friend_challenge_id,
                QuizSession.friend_challenge_round.is_not(None),
                QuizSession.friend_challenge_round < before_round,
                QuizSession.question_id.is_not(None),
            )
            .distinct()
            .order_by(QuizSession.question_id.asc())
        )
        result = await session.execute(stmt)
        return [question_id for question_id in result.scalars().all() if question_id is not None]

    @staticmethod
    async def has_daily_challenge_on_date(
        session: AsyncSession,
        *,
        user_id: int,
        local_date_berlin: date,
    ) -> bool:
        stmt = select(QuizSession.id).where(
            and_(
                QuizSession.user_id == user_id,
                QuizSession.source == "DAILY_CHALLENGE",
                QuizSession.local_date_berlin == local_date_berlin,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def create(session: AsyncSession, *, quiz_session: QuizSession) -> QuizSession:
        session.add(quiz_session)
        await session.flush()
        return quiz_session
