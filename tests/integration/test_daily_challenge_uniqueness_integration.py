from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_questions import QuizQuestion as QuizQuestionModel
from app.db.repo.daily_runs_repo import DailyRunsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.questions.runtime_bank import get_question_by_id
from app.game.sessions.errors import DailyChallengeAlreadyPlayedError
from app.game.sessions.service import GameSessionService
from app.game.sessions.types import AnswerSessionResult, StartSessionResult

UTC = timezone.utc


def _build_quick_mix_question(
    *,
    question_id: str,
    level: str,
    now_utc: datetime,
) -> QuizQuestionModel:
    return QuizQuestionModel(
        question_id=question_id,
        mode_code="QUICK_MIX_A1A2",
        source_file="daily_progress_seed.csv",
        level=level,
        category="DailyProgress",
        question_text=f"Daily {level} {question_id}?",
        option_1="a",
        option_2="b",
        option_3="c",
        option_4="d",
        correct_option_id=0,
        correct_answer="a",
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
            telegram_user_id=60_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="DailyChallenge",
            referred_by_user_id=None,
        )
        return int(user.id)


async def _start_daily(
    *,
    user_id: int,
    idempotency_key: str,
    now_utc: datetime,
) -> StartSessionResult:
    async with SessionLocal.begin() as session:
        return await GameSessionService.start_session(
            session,
            user_id=user_id,
            mode_code="DAILY_CHALLENGE",
            source="DAILY_CHALLENGE",
            idempotency_key=idempotency_key,
            now_utc=now_utc,
        )


async def _answer_daily_correctly(
    *,
    user_id: int,
    session_id: UUID,
    idempotency_key: str,
    now_utc: datetime,
) -> AnswerSessionResult:
    async with SessionLocal.begin() as session:
        quiz_session = await QuizSessionsRepo.get_by_id(session, session_id)
        assert quiz_session is not None
        question = await get_question_by_id(
            session,
            quiz_session.mode_code,
            question_id=quiz_session.question_id or "",
            local_date_berlin=quiz_session.local_date_berlin,
        )
        assert question is not None
        return await GameSessionService.submit_answer(
            session,
            user_id=user_id,
            session_id=session_id,
            selected_option=question.correct_option,
            idempotency_key=idempotency_key,
            now_utc=now_utc,
        )


@pytest.mark.asyncio
async def test_daily_retry_allowed_after_abandon() -> None:
    user_id = await _create_user("daily-retry-after-abandon")
    now_utc = datetime(2026, 2, 26, 7, 0, tzinfo=UTC)

    first_start = await _start_daily(
        user_id=user_id,
        idempotency_key="daily-retry:start:1",
        now_utc=now_utc,
    )
    async with SessionLocal.begin() as session:
        await GameSessionService.abandon_session(
            session,
            user_id=user_id,
            session_id=first_start.session.session_id,
            now_utc=now_utc + timedelta(seconds=1),
        )

    second_start = await _start_daily(
        user_id=user_id,
        idempotency_key="daily-retry:start:2",
        now_utc=now_utc + timedelta(seconds=2),
    )
    assert second_start.session.question_number == 1
    assert second_start.session.total_questions == 7
    assert second_start.session.session_id != first_start.session.session_id


@pytest.mark.asyncio
async def test_daily_blocks_after_first_completed_run_today() -> None:
    user_id = await _create_user("daily-block-after-completed")
    now_utc = datetime(2026, 2, 26, 8, 0, tzinfo=UTC)

    last_answer: AnswerSessionResult | None = None
    for idx in range(7):
        started = await _start_daily(
            user_id=user_id,
            idempotency_key=f"daily-complete:start:{idx}",
            now_utc=now_utc + timedelta(seconds=idx),
        )
        last_answer = await _answer_daily_correctly(
            user_id=user_id,
            session_id=started.session.session_id,
            idempotency_key=f"daily-complete:answer:{idx}",
            now_utc=now_utc + timedelta(seconds=30 + idx),
        )

    assert last_answer is not None
    assert last_answer.daily_completed is True
    assert last_answer.daily_current_question == 7

    with pytest.raises(DailyChallengeAlreadyPlayedError):
        await _start_daily(
            user_id=user_id,
            idempotency_key="daily-complete:start:blocked",
            now_utc=now_utc + timedelta(minutes=5),
        )

    async with SessionLocal.begin() as session:
        run = await DailyRunsRepo.get_by_user_date(
            session,
            user_id=user_id,
            berlin_date=now_utc.date(),
        )
        assert run is not None
        assert run.status == "COMPLETED"


@pytest.mark.asyncio
async def test_daily_questions_start_from_a1_and_progress_by_level() -> None:
    user_id = await _create_user("daily-level-progress")
    now_utc = datetime(2026, 2, 26, 8, 30, tzinfo=UTC)

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                _build_quick_mix_question(
                    question_id=f"daily_level_seed_{index}",
                    level=level,
                    now_utc=now_utc,
                )
                for index, level in enumerate(
                    ("A1", "A1", "A2", "A2", "B1", "B1", "B2", "B2"),
                    start=1,
                )
            ]
        )
        await session.flush()

    seen_levels: list[str] = []
    for idx in range(7):
        started = await _start_daily(
            user_id=user_id,
            idempotency_key=f"daily-level-progress:start:{idx}",
            now_utc=now_utc + timedelta(seconds=idx),
        )
        async with SessionLocal.begin() as session:
            selected = await session.get(QuizQuestionModel, started.session.question_id)
            assert selected is not None
            seen_levels.append(selected.level)

        await _answer_daily_correctly(
            user_id=user_id,
            session_id=started.session.session_id,
            idempotency_key=f"daily-level-progress:answer:{idx}",
            now_utc=now_utc + timedelta(seconds=40 + idx),
        )

    assert seen_levels[0] == "A1"
    level_order = {"A1": 0, "A2": 1, "B1": 2, "B2": 3}
    assert all(
        level_order[left] <= level_order[right] for left, right in zip(seen_levels, seen_levels[1:])
    )


@pytest.mark.asyncio
async def test_daily_questions_are_identical_for_different_users_same_day() -> None:
    first_user_id = await _create_user("daily-questions-user-1")
    second_user_id = await _create_user("daily-questions-user-2")
    now_utc = datetime(2026, 2, 26, 9, 0, tzinfo=UTC)

    first_sequence: list[str] = []
    second_sequence: list[str] = []

    for idx in range(7):
        started_first = await _start_daily(
            user_id=first_user_id,
            idempotency_key=f"daily-seq-1:start:{idx}",
            now_utc=now_utc + timedelta(seconds=idx),
        )
        first_sequence.append(started_first.session.question_id)
        await _answer_daily_correctly(
            user_id=first_user_id,
            session_id=started_first.session.session_id,
            idempotency_key=f"daily-seq-1:answer:{idx}",
            now_utc=now_utc + timedelta(seconds=40 + idx),
        )

        started_second = await _start_daily(
            user_id=second_user_id,
            idempotency_key=f"daily-seq-2:start:{idx}",
            now_utc=now_utc + timedelta(seconds=400 + idx),
        )
        second_sequence.append(started_second.session.question_id)
        await _answer_daily_correctly(
            user_id=second_user_id,
            session_id=started_second.session.session_id,
            idempotency_key=f"daily-seq-2:answer:{idx}",
            now_utc=now_utc + timedelta(seconds=440 + idx),
        )

    assert len(first_sequence) == 7
    assert first_sequence == second_sequence


@pytest.mark.asyncio
async def test_daily_double_submit_creates_single_attempt() -> None:
    user_id = await _create_user("daily-double-submit-guard")
    now_utc = datetime(2026, 2, 26, 10, 0, tzinfo=UTC)

    started = await _start_daily(
        user_id=user_id,
        idempotency_key="daily-double-submit:start:1",
        now_utc=now_utc,
    )
    first = await _answer_daily_correctly(
        user_id=user_id,
        session_id=started.session.session_id,
        idempotency_key="daily-double-submit:answer:1",
        now_utc=now_utc + timedelta(seconds=30),
    )
    second = await _answer_daily_correctly(
        user_id=user_id,
        session_id=started.session.session_id,
        idempotency_key="daily-double-submit:answer:2",
        now_utc=now_utc + timedelta(seconds=31),
    )

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert first.daily_run_id is not None

    async with SessionLocal.begin() as session:
        attempts_count = await session.scalar(
            select(func.count(QuizAttempt.id)).where(
                QuizAttempt.session_id == started.session.session_id,
            )
        )
        run = await DailyRunsRepo.get_by_id(session, first.daily_run_id)

    assert int(attempts_count or 0) == 1
    assert run is not None
    assert run.current_question == 1
