from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_sessions import QuizSession
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.mode_access_repo import ModeAccessRepo
from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.energy.service import EnergyService
from app.economy.streak.time import berlin_local_date
from app.game.modes.rules import is_mode_allowed, is_zero_cost_source
from app.game.questions.types import QuizQuestion
from app.game.sessions.errors import (
    DailyChallengeAlreadyPlayedError,
    EnergyInsufficientError,
    FriendChallengeAccessError,
    ModeLockedError,
    SessionNotFoundError,
)
from app.game.sessions.types import SessionQuestionView, StartSessionResult

from .levels import _is_persistent_adaptive_mode
from .progression import resolve_start_progression_state, select_level_weighted
from .question_loading import _build_start_result_from_existing_session


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
    if source == "FRIEND_CHALLENGE" and (
        friend_challenge_id is None or friend_challenge_round is None
    ):
        raise FriendChallengeAccessError

    existing = await QuizSessionsRepo.get_by_idempotency_key(session, idempotency_key)
    local_date = berlin_local_date(now_utc)
    if existing is not None:
        return await _build_start_result_from_existing_session(
            session,
            existing=existing,
            idempotent_replay=True,
        )

    if source == "DAILY_CHALLENGE":
        already_played = await QuizSessionsRepo.has_daily_challenge_on_date(
            session,
            user_id=user_id,
            local_date_berlin=local_date,
        )
        if already_played:
            raise DailyChallengeAlreadyPlayedError

    premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)
    has_mode_access = await ModeAccessRepo.has_active_access(
        session,
        user_id=user_id,
        mode_code=mode_code,
        now_utc=now_utc,
    )
    if not is_mode_allowed(
        mode_code=mode_code,
        premium_active=premium_active,
        has_mode_access=has_mode_access,
    ):
        raise ModeLockedError

    energy_free = 0
    energy_paid = 0
    energy_cost_total = 0
    if not is_zero_cost_source(source):
        energy_result = await EnergyService.consume_quiz(
            session,
            user_id=user_id,
            idempotency_key=f"energy:{idempotency_key}",
            now_utc=now_utc,
        )
        if not energy_result.allowed:
            raise EnergyInsufficientError
        energy_free = energy_result.free_energy
        energy_paid = energy_result.paid_energy
        energy_cost_total = 1

    question: QuizQuestion | None = None
    if forced_question_id is not None:
        from app.game.sessions import service as service_module

        question = await service_module.get_question_by_id(
            session,
            mode_code,
            question_id=forced_question_id,
            local_date_berlin=local_date,
        )

    if question is None:
        effective_preferred_level = preferred_question_level
        allowed_levels: tuple[str, ...] | None = None
        mix_step = 0
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

        recent_question_ids: list[str] = []
        if source != "FRIEND_CHALLENGE":
            recent_question_ids = await QuizAttemptsRepo.get_recent_question_ids_for_mode(
                session,
                user_id=user_id,
                mode_code=mode_code,
                limit=20,
            )
        selection_seed = selection_seed_override or idempotency_key
        if (
            _is_persistent_adaptive_mode(mode_code=mode_code)
            and effective_preferred_level is not None
        ):
            effective_preferred_level = select_level_weighted(
                effective_preferred_level,
                mix_step,
                selection_seed=selection_seed,
            )
        from app.game.sessions import service as service_module

        question = await service_module.select_question_for_mode(
            session,
            mode_code,
            local_date_berlin=local_date,
            recent_question_ids=recent_question_ids,
            selection_seed=selection_seed,
            preferred_level=effective_preferred_level,
            allowed_levels=allowed_levels,
        )

    try:
        created = await QuizSessionsRepo.create(
            session,
            quiz_session=QuizSession(
                id=uuid4(),
                user_id=user_id,
                mode_code=mode_code,
                source=source,
                status="STARTED",
                energy_cost_total=energy_cost_total,
                question_id=question.question_id,
                friend_challenge_id=friend_challenge_id,
                friend_challenge_round=friend_challenge_round,
                started_at=now_utc,
                local_date_berlin=local_date,
                idempotency_key=idempotency_key,
            ),
        )
    except IntegrityError as exc:
        if source == "DAILY_CHALLENGE":
            raise DailyChallengeAlreadyPlayedError from exc
        raise

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


async def get_session_user_id(session: AsyncSession, session_id: UUID) -> int:
    quiz_session = await QuizSessionsRepo.get_by_id(session, session_id)
    if quiz_session is None:
        raise SessionNotFoundError
    return quiz_session.user_id
