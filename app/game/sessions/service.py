from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.mode_access_repo import ModeAccessRepo
from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.energy.service import EnergyService
from app.economy.streak.service import StreakService
from app.economy.streak.time import berlin_local_date
from app.game.modes.rules import is_mode_allowed, is_zero_cost_source
from app.game.questions.static_bank import (
    get_question_by_id,
    get_question_for_mode,
    select_question_for_mode,
)
from app.game.sessions.errors import (
    DailyChallengeAlreadyPlayedError,
    EnergyInsufficientError,
    InvalidAnswerOptionError,
    ModeLockedError,
    SessionNotFoundError,
)
from app.game.sessions.types import AnswerSessionResult, SessionQuestionView, StartSessionResult


class GameSessionService:
    @staticmethod
    async def start_session(
        session: AsyncSession,
        *,
        user_id: int,
        mode_code: str,
        source: str,
        idempotency_key: str,
        now_utc: datetime,
    ) -> StartSessionResult:
        existing = await QuizSessionsRepo.get_by_idempotency_key(session, idempotency_key)
        local_date = berlin_local_date(now_utc)

        if existing is not None:
            question = None
            if existing.question_id is not None:
                question = get_question_by_id(
                    existing.mode_code,
                    question_id=existing.question_id,
                    local_date_berlin=existing.local_date_berlin,
                )
            if question is None:
                question = get_question_for_mode(
                    existing.mode_code,
                    local_date_berlin=existing.local_date_berlin,
                )

            return StartSessionResult(
                session=SessionQuestionView(
                    session_id=existing.id,
                    question_id=question.question_id,
                    text=question.text,
                    options=question.options,
                    mode_code=existing.mode_code,
                    source=existing.source,
                ),
                energy_free=0,
                energy_paid=0,
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

        recent_question_ids = await QuizAttemptsRepo.get_recent_question_ids_for_mode(
            session,
            user_id=user_id,
            mode_code=mode_code,
            limit=20,
        )
        question = select_question_for_mode(
            mode_code,
            local_date_berlin=local_date,
            recent_question_ids=recent_question_ids,
            selection_seed=idempotency_key,
        )

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
                started_at=now_utc,
                local_date_berlin=local_date,
                idempotency_key=idempotency_key,
            ),
        )

        return StartSessionResult(
            session=SessionQuestionView(
                session_id=created.id,
                question_id=question.question_id,
                text=question.text,
                options=question.options,
                mode_code=mode_code,
                source=source,
            ),
            energy_free=energy_free,
            energy_paid=energy_paid,
            idempotent_replay=False,
        )

    @staticmethod
    async def submit_answer(
        session: AsyncSession,
        *,
        user_id: int,
        session_id: UUID,
        selected_option: int,
        idempotency_key: str,
        now_utc: datetime,
    ) -> AnswerSessionResult:
        if selected_option < 0 or selected_option > 3:
            raise InvalidAnswerOptionError

        existing_attempt = await QuizAttemptsRepo.get_by_idempotency_key(session, idempotency_key)
        if existing_attempt is not None:
            streak_snapshot = await StreakService.sync_rollover(session, user_id=user_id, now_utc=now_utc)
            return AnswerSessionResult(
                session_id=session_id,
                question_id=existing_attempt.question_id,
                is_correct=existing_attempt.is_correct,
                current_streak=streak_snapshot.current_streak,
                best_streak=streak_snapshot.best_streak,
                idempotent_replay=True,
            )

        quiz_session = await QuizSessionsRepo.get_by_id_for_update(session, session_id)
        if quiz_session is None or quiz_session.user_id != user_id:
            raise SessionNotFoundError

        question = None
        if quiz_session.question_id is not None:
            question = get_question_by_id(
                quiz_session.mode_code,
                question_id=quiz_session.question_id,
                local_date_berlin=quiz_session.local_date_berlin,
            )
        if question is None:
            question = get_question_for_mode(
                quiz_session.mode_code,
                local_date_berlin=quiz_session.local_date_berlin,
            )

        is_correct = selected_option == question.correct_option

        await QuizAttemptsRepo.create(
            session,
            attempt=QuizAttempt(
                session_id=quiz_session.id,
                user_id=user_id,
                question_id=question.question_id,
                is_correct=is_correct,
                answered_at=now_utc,
                response_ms=0,
                idempotency_key=idempotency_key,
            ),
        )

        quiz_session.status = "COMPLETED"
        quiz_session.completed_at = now_utc

        streak_result = await StreakService.record_activity(
            session,
            user_id=user_id,
            activity_at_utc=now_utc,
        )
        return AnswerSessionResult(
            session_id=quiz_session.id,
            question_id=question.question_id,
            is_correct=is_correct,
            current_streak=streak_result.current_streak,
            best_streak=streak_result.best_streak,
            idempotent_replay=False,
        )

    @staticmethod
    async def get_session_user_id(session: AsyncSession, session_id: UUID) -> int:
        quiz_session = await QuizSessionsRepo.get_by_id(session, session_id)
        if quiz_session is None:
            raise SessionNotFoundError
        return quiz_session.user_id
