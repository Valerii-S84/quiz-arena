from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_sessions import QuizSession
from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.energy.service import EnergyService
from app.economy.streak.time import berlin_local_date
from app.game.modes.rules import is_zero_cost_source
from app.game.questions.types import QuizQuestion
from app.game.sessions.errors import (
    EnergyInsufficientError,
    FriendChallengeAccessError,
    SessionNotFoundError,
)
from app.game.sessions.types import SessionQuestionView, StartSessionResult

from .levels import _is_persistent_adaptive_mode
from .progression import resolve_start_progression_state, select_level_weighted
from .question_loading import _build_start_result_from_existing_session
from .sessions_start_daily import start_daily_session


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


async def _get_forced_question(
    session: AsyncSession,
    *,
    mode_code: str,
    local_date: date,
    forced_question_id: str | None,
) -> QuizQuestion | None:
    if forced_question_id is None:
        return None

    from app.game.sessions import service as service_module

    return await service_module.get_question_by_id(
        session,
        mode_code,
        question_id=forced_question_id,
        local_date_berlin=local_date,
    )


async def _resolve_start_progression_preferences(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    preferred_question_level: str | None,
    now_utc: datetime,
) -> tuple[str | None, int, tuple[str, ...] | None]:
    effective_preferred_level = preferred_question_level
    mix_step = 0
    allowed_levels: tuple[str, ...] | None = None
    if _is_persistent_adaptive_mode(mode_code=mode_code):
        (
            effective_preferred_level,
            mix_step,
            allowed_levels,
        ) = await resolve_start_progression_state(
            session,
            user_id=user_id,
            mode_code=mode_code,
            preferred_level_override=effective_preferred_level,
            now_utc=now_utc,
        )
    return effective_preferred_level, mix_step, allowed_levels


async def _get_recent_question_ids_for_start(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
) -> list[str]:
    if source == "FRIEND_CHALLENGE":
        return []
    return await QuizAttemptsRepo.get_recent_question_ids_for_mode(
        session,
        user_id=user_id,
        mode_code=mode_code,
        limit=20,
    )


async def _select_question_for_start(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    idempotency_key: str,
    local_date: date,
    selection_seed_override: str | None,
    preferred_question_level: str | None,
    now_utc: datetime,
) -> QuizQuestion:
    (
        effective_preferred_level,
        mix_step,
        allowed_levels,
    ) = await _resolve_start_progression_preferences(
        session,
        user_id=user_id,
        mode_code=mode_code,
        preferred_question_level=preferred_question_level,
        now_utc=now_utc,
    )
    recent_question_ids = await _get_recent_question_ids_for_start(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source=source,
    )
    selection_seed = selection_seed_override or idempotency_key
    if _is_persistent_adaptive_mode(mode_code=mode_code) and effective_preferred_level is not None:
        effective_preferred_level = select_level_weighted(
            effective_preferred_level,
            mix_step,
            selection_seed=selection_seed,
        )

    from app.game.sessions import service as service_module

    return await service_module.select_question_for_mode(
        session,
        mode_code,
        local_date_berlin=local_date,
        recent_question_ids=recent_question_ids,
        selection_seed=selection_seed,
        preferred_level=effective_preferred_level,
        allowed_levels=allowed_levels,
    )


async def _resolve_question_for_start(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    idempotency_key: str,
    local_date: date,
    selection_seed_override: str | None,
    preferred_question_level: str | None,
    forced_question_id: str | None,
    now_utc: datetime,
) -> QuizQuestion:
    question = await _get_forced_question(
        session,
        mode_code=mode_code,
        local_date=local_date,
        forced_question_id=forced_question_id,
    )
    if question is not None:
        return question
    return await _select_question_for_start(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source=source,
        idempotency_key=idempotency_key,
        local_date=local_date,
        selection_seed_override=selection_seed_override,
        preferred_question_level=preferred_question_level,
        now_utc=now_utc,
    )


def _build_start_session_result(
    *,
    created: QuizSession,
    question: QuizQuestion,
    mode_code: str,
    source: str,
    energy_free: int,
    energy_paid: int,
    friend_challenge_round: int | None,
    friend_challenge_total_rounds: int | None,
) -> StartSessionResult:
    return StartSessionResult(
        session=SessionQuestionView(
            session_id=created.id,
            question_id=question.question_id,
            text=question.text,
            options=question.options,
            mode_code=mode_code,
            source=source,
            category=question.category,
            question_number=(friend_challenge_round if source == "FRIEND_CHALLENGE" else 1),
            total_questions=(friend_challenge_total_rounds if source == "FRIEND_CHALLENGE" else 1),
        ),
        energy_free=energy_free,
        energy_paid=energy_paid,
        idempotent_replay=False,
    )


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
    question = await _resolve_question_for_start(
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

    return _build_start_session_result(
        created=created,
        question=question,
        mode_code=mode_code,
        source=source,
        energy_free=energy_free,
        energy_paid=energy_paid,
        friend_challenge_round=friend_challenge_round,
        friend_challenge_total_rounds=friend_challenge_total_rounds,
    )


async def get_session_user_id(session: AsyncSession, session_id: UUID) -> int:
    quiz_session = await QuizSessionsRepo.get_by_id(session, session_id)
    if quiz_session is None:
        raise SessionNotFoundError
    return quiz_session.user_id
