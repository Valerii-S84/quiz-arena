from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.streak.time import berlin_local_date
from app.game.sessions.errors import FriendChallengeAccessError
from app.game.sessions.types import StartSessionResult

from .question_loading import _build_start_result_from_existing_session
from .sessions_start_daily import start_daily_session


def ensure_friend_challenge_start_args(
    *,
    source: str,
    friend_challenge_id: UUID | None,
    friend_challenge_round: int | None,
) -> None:
    if source == "FRIEND_CHALLENGE" and (
        friend_challenge_id is None or friend_challenge_round is None
    ):
        raise FriendChallengeAccessError


async def get_idempotent_start_result(
    session: AsyncSession,
    *,
    idempotency_key: str,
) -> StartSessionResult | None:
    existing = await QuizSessionsRepo.get_by_idempotency_key(session, idempotency_key)
    if existing is None:
        return None
    return await _build_start_result_from_existing_session(
        session,
        existing=existing,
        idempotent_replay=True,
    )


async def get_existing_or_daily_start_result(
    session: AsyncSession,
    *,
    user_id: int,
    source: str,
    idempotency_key: str,
    now_utc: datetime,
) -> tuple[date, StartSessionResult | None]:
    local_date = berlin_local_date(now_utc)
    existing = await get_idempotent_start_result(session, idempotency_key=idempotency_key)
    if existing is not None:
        return local_date, existing
    if source != "DAILY_CHALLENGE":
        return local_date, None
    return local_date, await start_daily_session(
        session,
        user_id=user_id,
        idempotency_key=idempotency_key,
        local_date=local_date,
        now_utc=now_utc,
    )
