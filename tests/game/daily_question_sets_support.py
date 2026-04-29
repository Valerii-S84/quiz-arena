from __future__ import annotations

import pytest

from app.db.repo.quiz_questions_repo import QuizQuestionPoolCandidate, QuizQuestionsRepo

DAILY_TEST_LEVELS = ("A1", "A1", "A2", "A2", "A2", "B1", "B1")


def candidate(
    question_id: str,
    *,
    level: str,
    source_file: str,
    category: str,
) -> QuizQuestionPoolCandidate:
    return QuizQuestionPoolCandidate(
        question_id=question_id,
        level=level,
        source_file=source_file,
        category=category,
    )


def install_daily_candidate_repo(
    monkeypatch: pytest.MonkeyPatch,
    candidates: tuple[QuizQuestionPoolCandidate, ...],
) -> list[tuple[str, ...]]:
    all_active_calls: list[tuple[str, ...]] = []

    async def fake_list_question_candidates_all_active(  # noqa: ANN001
        session,
        *,
        exclude_question_ids=None,
        preferred_levels=None,
        require_quick_mix_eligible=False,
    ):
        assert exclude_question_ids is None
        assert require_quick_mix_eligible is True
        level_filter = tuple(preferred_levels or ())
        all_active_calls.append(level_filter)
        return [question for question in candidates if question.level in level_filter]

    async def fail_list_question_candidates_for_mode(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("Daily Challenge must use quick_mix_eligible candidate semantics")

    monkeypatch.setattr(
        QuizQuestionsRepo,
        "list_question_candidates_all_active",
        fake_list_question_candidates_all_active,
    )
    monkeypatch.setattr(
        QuizQuestionsRepo,
        "list_question_candidates_for_mode",
        fail_list_question_candidates_for_mode,
    )
    return all_active_calls
