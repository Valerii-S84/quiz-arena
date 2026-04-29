from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


async def test_quiz_session_lookups_create_counts_and_duration_queries() -> None:
    session_id = uuid4()
    challenge_id = uuid4()
    quiz_session = QuizSession(id=session_id, user_id=7, question_id="q1", status="STARTED")

    get_session = RecordingSession(get_result=quiz_session)
    assert await QuizSessionsRepo.get_by_id(get_session, session_id) is quiz_session
    assert get_session.get_calls == [(QuizSession, session_id)]

    lock_session = RecordingSession(_ScalarResult(quiz_session))
    await QuizSessionsRepo.get_by_id_for_update(lock_session, session_id)
    assert "FOR UPDATE" in compile_statement(lock_session.statement)

    key_session = RecordingSession(_ScalarResult(None))
    await QuizSessionsRepo.get_by_idempotency_key(key_session, "quiz:key")
    assert "quiz_sessions.idempotency_key = 'quiz:key'" in compile_statement(key_session.statement)

    round_session = RecordingSession(_ScalarResult(quiz_session))
    await QuizSessionsRepo.get_by_friend_challenge_round_user(
        round_session,
        friend_challenge_id=challenge_id,
        friend_challenge_round=2,
        user_id=7,
    )
    round_sql = compile_statement(round_session.statement)
    assert "quiz_sessions.friend_challenge_round = 2" in round_sql
    assert "quiz_sessions.user_id = 7" in round_sql

    any_user_session = RecordingSession(_ScalarResult(quiz_session))
    await QuizSessionsRepo.get_by_friend_challenge_round_any_user(
        any_user_session,
        friend_challenge_id=challenge_id,
        friend_challenge_round=2,
    )
    assert "ORDER BY quiz_sessions.started_at ASC, quiz_sessions.id ASC" in compile_statement(
        any_user_session.statement
    )

    question_session = RecordingSession(_ScalarsResult(["q1", None, "q2"]))
    assert await QuizSessionsRepo.list_friend_challenge_question_ids_before_round(
        question_session,
        friend_challenge_id=challenge_id,
        before_round=3,
    ) == ["q1", "q2"]

    daily_session = RecordingSession(_ScalarResult(session_id))
    assert await QuizSessionsRepo.has_daily_challenge_on_date(
        daily_session,
        user_id=7,
        local_date_berlin=date(2026, 3, 14),
    )

    active_session = RecordingSession(_ScalarResult(quiz_session))
    await QuizSessionsRepo.get_active_daily_session_for_run(active_session, daily_run_id=uuid4())
    assert "quiz_sessions.status = 'STARTED'" in compile_statement(active_session.statement)

    create_session = RecordingSession()
    assert await QuizSessionsRepo.create(create_session, quiz_session=quiz_session) is quiz_session
    assert create_session.flushed is True

    count_session = RecordingSession(_ScalarResult(None))
    assert await QuizSessionsRepo.count_completed_for_user(count_session, user_id=7) == 0

    duration_session = RecordingSession(_ScalarResult(-250))
    assert (
        await QuizSessionsRepo.sum_completed_duration_ms_for_friend_challenge_user(
            duration_session,
            friend_challenge_id=challenge_id,
            user_id=7,
        )
        == 0
    )


async def test_quiz_attempt_queries_cover_latest_recent_and_activity_counts() -> None:
    session_id = uuid4()
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    attempt = QuizAttempt(
        id=10,
        session_id=session_id,
        user_id=7,
        question_id="q1",
        is_correct=True,
        answered_at=now_utc,
        response_ms=1200,
        idempotency_key="attempt:key",
    )

    key_session = RecordingSession(_ScalarResult(attempt))
    assert await QuizAttemptsRepo.get_by_idempotency_key(key_session, "attempt:key") is attempt
    assert "quiz_attempts.idempotency_key = 'attempt:key'" in compile_statement(
        key_session.statement
    )

    create_session = RecordingSession()
    assert await QuizAttemptsRepo.create(create_session, attempt=attempt) is attempt
    assert create_session.added == [attempt]

    latest_session = RecordingSession(_ScalarResult(attempt))
    await QuizAttemptsRepo.get_latest_for_session(latest_session, session_id=session_id)
    assert "ORDER BY quiz_attempts.answered_at DESC" in compile_statement(latest_session.statement)

    recent_session = RecordingSession(_ScalarsResult(["q3", "q2"]))
    assert await QuizAttemptsRepo.get_recent_question_ids_for_mode(
        recent_session,
        user_id=7,
        mode_code="DAILY_CUP",
        limit=2,
    ) == ["q3", "q2"]
    recent_sql = compile_statement(recent_session.statement)
    assert "JOIN quiz_sessions ON quiz_attempts.session_id = quiz_sessions.id" in recent_sql
    assert "quiz_sessions.mode_code = 'DAILY_CUP'" in recent_sql

    attempts_session = RecordingSession(_ScalarResult(5))
    assert (
        await QuizAttemptsRepo.count_user_attempts_between(
            attempts_session,
            user_id=7,
            from_utc=now_utc,
            to_utc=now_utc,
        )
        == 5
    )

    days_session = RecordingSession(_ScalarResult(None))
    assert (
        await QuizAttemptsRepo.count_user_active_local_days_between(
            days_session,
            user_id=7,
            from_utc=now_utc,
            to_utc=now_utc,
        )
        == 0
    )
