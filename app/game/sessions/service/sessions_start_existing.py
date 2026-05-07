from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_sessions import QuizSession
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.sessions.errors import FriendChallengeAccessError, SessionNotFoundError


async def get_session_user_id(session: AsyncSession, session_id: UUID) -> int:
    quiz_session = await QuizSessionsRepo.get_by_id(session, session_id)
    if quiz_session is None:
        raise SessionNotFoundError
    return quiz_session.user_id


def _session_question_number(
    *,
    source: str,
    friend_challenge_round: int | None,
    arena_round: int | None,
) -> int:
    if source == "FRIEND_CHALLENGE":
        return friend_challenge_round or 1
    if source == "ARENA_DUEL":
        return arena_round or 1
    return 1


def _session_total_questions(
    *,
    source: str,
    friend_challenge_total_rounds: int | None,
) -> int:
    if source == "FRIEND_CHALLENGE":
        return friend_challenge_total_rounds or 1
    if source == "ARENA_DUEL":
        return DUEL_QUESTION_COUNT
    return 1


def _ensure_existing_session_matches_start_request(
    existing: QuizSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    friend_challenge_id: UUID | None,
    friend_challenge_round: int | None,
    arena_attempt_id: UUID | None,
    arena_round: int | None,
) -> None:
    if existing.user_id != user_id or existing.mode_code != mode_code or existing.source != source:
        raise FriendChallengeAccessError

    if source == "FRIEND_CHALLENGE":
        if (
            friend_challenge_id is None
            or friend_challenge_round is None
            or existing.friend_challenge_id != friend_challenge_id
            or existing.friend_challenge_round != friend_challenge_round
        ):
            raise FriendChallengeAccessError
        return

    if source == "ARENA_DUEL":
        if (
            arena_attempt_id is None
            or arena_round is None
            or existing.arena_attempt_id != arena_attempt_id
            or existing.arena_round != arena_round
        ):
            raise FriendChallengeAccessError
