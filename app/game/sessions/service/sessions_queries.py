from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.game.sessions.errors import SessionNotFoundError


async def get_session_user_id(session: AsyncSession, session_id: UUID) -> int:
    quiz_session = await QuizSessionsRepo.get_by_id(session, session_id)
    if quiz_session is None:
        raise SessionNotFoundError
    return quiz_session.user_id
