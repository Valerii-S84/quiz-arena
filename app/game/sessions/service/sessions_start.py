from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_sessions import QuizSession
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.energy.service import EnergyService
from app.economy.streak.time import berlin_local_date
from app.game.modes.rules import is_zero_cost_source
from app.game.sessions.errors import (
    EnergyInsufficientError,
    FriendChallengeAccessError,
    SessionNotFoundError,
)
from app.game.sessions.types import StartSessionResult

from .question_loading import (
    _build_start_result_from_created_session,
    _build_start_result_from_existing_session,
)
from .sessions_start_daily import start_daily_session
from .sessions_start_question_selection import resolve_start_question


def _ensure_friend_challenge_start_args(
    *,
    source: str,
    friend_challenge_id: UUID | None,
    friend_challenge_round: int | None,
) -> None:
    if source == "FRIEND_CHALLENGE" and (
        friend_challenge_id is None or friend_challenge_round is None
    ):
        raise FriendChallengeAccessError


async def _get_idempotent_start_result(
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


async def _get_existing_or_daily_start_result(
    session: AsyncSession,
    *,
    user_id: int,
    source: str,
    idempotency_key: str,
    now_utc: datetime,
) -> tuple[date, StartSessionResult | None]:
    local_date = berlin_local_date(now_utc)
    existing = await _get_idempotent_start_result(session, idempotency_key=idempotency_key)
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


async def _consume_start_energy(
    session: AsyncSession,
    *,
    user_id: int,
    source: str,
    idempotency_key: str,
    now_utc: datetime,
) -> tuple[int, int, int]:
    if is_zero_cost_source(source):
        return 0, 0, 0

    energy_result = await EnergyService.consume_quiz(
        session,
        user_id=user_id,
        idempotency_key=f"energy:{idempotency_key}",
        now_utc=now_utc,
    )
    if not energy_result.allowed:
        raise EnergyInsufficientError
    return energy_result.free_energy, energy_result.paid_energy, 1


async def _create_started_session(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    energy_cost_total: int,
    question_id: str,
    friend_challenge_id: UUID | None,
    friend_challenge_round: int | None,
    now_utc: datetime,
    local_date: date,
    idempotency_key: str,
) -> QuizSession:
    return await QuizSessionsRepo.create(
        session,
        quiz_session=QuizSession(
            id=uuid4(),
            user_id=user_id,
            mode_code=mode_code,
            source=source,
            status="STARTED",
            energy_cost_total=energy_cost_total,
            question_id=question_id,
            friend_challenge_id=friend_challenge_id,
            friend_challenge_round=friend_challenge_round,
            started_at=now_utc,
            local_date_berlin=local_date,
            idempotency_key=idempotency_key,
        ),
    )


async def start_session(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    idempotency_key: str,
    now_utc: datetime,
    selection_seed_override: str | None = None,
    preferred_question_level: str | None = None,
    forced_question_id: str | None = None,
    friend_challenge_id: UUID | None = None,
    friend_challenge_round: int | None = None,
    friend_challenge_total_rounds: int | None = None,
) -> StartSessionResult:
    _ensure_friend_challenge_start_args(
        source=source,
        friend_challenge_id=friend_challenge_id,
        friend_challenge_round=friend_challenge_round,
    )

    local_date, prebuilt_result = await _get_existing_or_daily_start_result(
        session,
        user_id=user_id,
        source=source,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )
    if prebuilt_result is not None:
        return prebuilt_result

    energy_free, energy_paid, energy_cost_total = await _consume_start_energy(
        session,
        user_id=user_id,
        source=source,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )
    question = await resolve_start_question(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source=source,
        idempotency_key=idempotency_key,
        local_date=local_date,
        selection_seed_override=selection_seed_override,
        preferred_question_level=preferred_question_level,
        forced_question_id=forced_question_id,
        now_utc=now_utc,
    )
    created = await _create_started_session(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source=source,
        energy_cost_total=energy_cost_total,
        question_id=question.question_id,
        friend_challenge_id=friend_challenge_id,
        friend_challenge_round=friend_challenge_round,
        now_utc=now_utc,
        local_date=local_date,
        idempotency_key=idempotency_key,
    )

    return _build_start_result_from_created_session(
        created=created,
        question=question,
        energy_free=energy_free,
        energy_paid=energy_paid,
        friend_challenge_total_rounds=friend_challenge_total_rounds,
    )


async def get_session_user_id(session: AsyncSession, session_id: UUID) -> int:
    quiz_session = await QuizSessionsRepo.get_by_id(session, session_id)
    if quiz_session is None:
        raise SessionNotFoundError
    return quiz_session.user_id
