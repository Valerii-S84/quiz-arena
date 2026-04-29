from __future__ import annotations

from datetime import datetime, timezone

from app.db.models.quiz_questions import QuizQuestion
from app.db.repo.quiz_questions_repo import QuizQuestionPoolChange, QuizQuestionsRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


async def test_quiz_question_queries_filter_optional_pools_and_map_changes() -> None:
    question = QuizQuestion(
        question_id="q1",
        mode_code="DAILY_CUP",
        source_file="bank.csv",
        level="A1",
        category="Grammatik",
        status="ACTIVE",
        question_text="Frage?",
        option_1="Antwort",
        option_2="Falsch",
        option_3="Falsch",
        option_4="Falsch",
        correct_option_id=0,
        correct_answer="Antwort",
        explanation="Erklärung",
        key="q1",
        quick_mix_eligible=True,
        created_at=datetime(2026, 3, 14, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 14, 12, 0, tzinfo=UTC),
    )

    get_session = RecordingSession(get_result=question)
    assert await QuizQuestionsRepo.get_by_id(get_session, "q1") is question
    assert get_session.get_calls == [(QuizQuestion, "q1")]

    mode_session = RecordingSession(_ScalarsResult(["q1"]))
    assert await QuizQuestionsRepo.list_question_ids_for_mode(
        mode_session,
        mode_code="DAILY_CUP",
        exclude_question_ids=["q0"],
        preferred_levels=["A1"],
    ) == ["q1"]
    mode_sql = compile_statement(mode_session.statement)
    assert "quiz_questions.level IN ('A1')" in mode_sql
    assert "(quiz_questions.question_id NOT IN ('q0'))" in mode_sql

    all_session = RecordingSession(_ScalarsResult(["q1"]))
    await QuizQuestionsRepo.list_question_ids_all_active(
        all_session,
        exclude_question_ids=["q0"],
        preferred_levels=["A1"],
        require_quick_mix_eligible=True,
    )
    assert "quiz_questions.quick_mix_eligible IS true" in compile_statement(all_session.statement)

    empty_ids_session = RecordingSession()
    assert await QuizQuestionsRepo.list_by_ids(empty_ids_session, question_ids=[]) == []

    ids_session = RecordingSession(_ScalarsResult([question]))
    assert await QuizQuestionsRepo.list_by_ids(ids_session, question_ids=["q1"]) == [question]

    change_time = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    changes_session = RecordingSession(
        _RowsResult([("q1", "DAILY_CUP", "A1", "ACTIVE", True, change_time)])
    )
    assert await QuizQuestionsRepo.list_question_pool_changes_since(
        changes_session,
        since_updated_at=change_time,
    ) == [
        QuizQuestionPoolChange(
            question_id="q1",
            mode_code="DAILY_CUP",
            level="A1",
            status="ACTIVE",
            quick_mix_eligible=True,
            updated_at=change_time,
        )
    ]
