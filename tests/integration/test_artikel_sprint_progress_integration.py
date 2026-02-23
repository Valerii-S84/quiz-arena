from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.db.models.mode_progress import ModeProgress
from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_questions import QuizQuestion as QuizQuestionModel
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.streak.time import berlin_local_date
from app.game.sessions.service import GameSessionService

UTC = timezone.utc


def _build_artikel_question(
    *,
    question_id: str,
    level: str,
    now_utc: datetime,
) -> QuizQuestionModel:
    return QuizQuestionModel(
        question_id=question_id,
        mode_code="ARTIKEL_SPRINT",
        source_file="artikel_progress_seed.csv",
        level=level,
        category="Artikel",
        question_text=f"Artikel {level} {question_id}?",
        option_1="der",
        option_2="die",
        option_3="das",
        option_4="dem",
        correct_option_id=0,
        correct_answer="der",
        explanation="Seed",
        key=question_id,
        status="ACTIVE",
        created_at=now_utc,
        updated_at=now_utc,
    )


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=40_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="Artikel",
            referred_by_user_id=None,
        )
        return user.id


@pytest.mark.asyncio
async def test_artikel_sprint_first_question_starts_from_a1() -> None:
    now_utc = datetime(2026, 2, 19, 22, 0, tzinfo=UTC)
    user_id = await _create_user("artikel_start_a1")

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                _build_artikel_question(
                    question_id="artikel_start_a1_001",
                    level="A1",
                    now_utc=now_utc,
                ),
                _build_artikel_question(
                    question_id="artikel_start_b2_001",
                    level="B2",
                    now_utc=now_utc,
                ),
            ]
        )
        await session.flush()

        start = await GameSessionService.start_session(
            session,
            user_id=user_id,
            mode_code="ARTIKEL_SPRINT",
            source="MENU",
            idempotency_key="artikel:first:start",
            now_utc=now_utc,
        )

        question = await session.get(QuizQuestionModel, start.session.question_id)
        assert question is not None
        assert question.level == "A1"


@pytest.mark.asyncio
async def test_artikel_sprint_persists_level_between_sessions_and_days() -> None:
    now_utc = datetime(2026, 2, 19, 22, 30, tzinfo=UTC)
    user_id = await _create_user("artikel_progress_persist")

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                _build_artikel_question(
                    question_id="artikel_progress_a1_001",
                    level="A1",
                    now_utc=now_utc,
                ),
                _build_artikel_question(
                    question_id="artikel_progress_a2_001",
                    level="A2",
                    now_utc=now_utc,
                ),
                _build_artikel_question(
                    question_id="artikel_progress_b1_001",
                    level="B1",
                    now_utc=now_utc,
                ),
                _build_artikel_question(
                    question_id="artikel_progress_b2_001",
                    level="B2",
                    now_utc=now_utc,
                ),
            ]
        )
        await session.flush()

        first = await GameSessionService.start_session(
            session,
            user_id=user_id,
            mode_code="ARTIKEL_SPRINT",
            source="MENU",
            idempotency_key="artikel:progress:first:start",
            now_utc=now_utc,
        )
        first_question = await session.get(QuizQuestionModel, first.session.question_id)
        assert first_question is not None
        assert first_question.level == "A1"

        first_answer = await GameSessionService.submit_answer(
            session,
            user_id=user_id,
            session_id=first.session.session_id,
            selected_option=0,
            idempotency_key="artikel:progress:first:answer",
            now_utc=now_utc,
        )
        assert first_answer.next_preferred_level == "A2"

        second = await GameSessionService.start_session(
            session,
            user_id=user_id,
            mode_code="ARTIKEL_SPRINT",
            source="MENU",
            idempotency_key="artikel:progress:second:start",
            now_utc=now_utc + timedelta(minutes=1),
        )
        second_question = await session.get(QuizQuestionModel, second.session.question_id)
        assert second_question is not None
        assert second_question.level == "A2"

        second_answer = await GameSessionService.submit_answer(
            session,
            user_id=user_id,
            session_id=second.session.session_id,
            selected_option=0,
            idempotency_key="artikel:progress:second:answer",
            now_utc=now_utc + timedelta(minutes=1),
        )
        assert second_answer.next_preferred_level == "B1"

        progress_row = await session.get(
            ModeProgress,
            {
                "user_id": user_id,
                "mode_code": "ARTIKEL_SPRINT",
            },
        )
        assert progress_row is not None
        assert progress_row.preferred_level == "B1"

        next_day = await GameSessionService.start_session(
            session,
            user_id=user_id,
            mode_code="ARTIKEL_SPRINT",
            source="MENU",
            idempotency_key="artikel:progress:next_day:start",
            now_utc=now_utc + timedelta(days=1),
        )
        next_day_question = await session.get(QuizQuestionModel, next_day.session.question_id)
        assert next_day_question is not None
        assert next_day_question.level == "B1"


@pytest.mark.asyncio
async def test_artikel_sprint_backfills_progress_from_recent_history_when_row_missing() -> None:
    now_utc = datetime(2026, 2, 19, 23, 0, tzinfo=UTC)
    user_id = await _create_user("artikel_progress_backfill")

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                _build_artikel_question(
                    question_id="artikel_backfill_a1_001",
                    level="A1",
                    now_utc=now_utc,
                ),
                _build_artikel_question(
                    question_id="artikel_backfill_b1_001",
                    level="B1",
                    now_utc=now_utc,
                ),
            ]
        )
        await session.flush()

        legacy_session_id = uuid4()
        session.add(
            QuizSession(
                id=legacy_session_id,
                user_id=user_id,
                mode_code="ARTIKEL_SPRINT",
                source="MENU",
                status="COMPLETED",
                energy_cost_total=1,
                question_id="artikel_backfill_b1_001",
                friend_challenge_id=None,
                friend_challenge_round=None,
                started_at=now_utc - timedelta(days=1, minutes=1),
                completed_at=now_utc - timedelta(days=1),
                local_date_berlin=berlin_local_date(now_utc - timedelta(days=1)),
                idempotency_key=f"artikel:legacy:session:{uuid4().hex}",
            )
        )
        await session.flush()

        session.add(
            QuizAttempt(
                session_id=legacy_session_id,
                user_id=user_id,
                question_id="artikel_backfill_b1_001",
                is_correct=True,
                answered_at=now_utc - timedelta(days=1),
                response_ms=0,
                idempotency_key=f"artikel:legacy:attempt:{uuid4().hex}",
            )
        )
        await session.flush()

        backfilled = await GameSessionService.start_session(
            session,
            user_id=user_id,
            mode_code="ARTIKEL_SPRINT",
            source="MENU",
            idempotency_key="artikel:backfill:start",
            now_utc=now_utc,
        )
        backfilled_question = await session.get(QuizQuestionModel, backfilled.session.question_id)
        assert backfilled_question is not None
        assert backfilled_question.level == "B1"

        progress_row = await session.get(
            ModeProgress,
            {
                "user_id": user_id,
                "mode_code": "ARTIKEL_SPRINT",
            },
        )
        assert progress_row is not None
        assert progress_row.preferred_level == "B1"
