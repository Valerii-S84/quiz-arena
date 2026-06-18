from __future__ import annotations

from collections.abc import Callable, Mapping
from types import SimpleNamespace

import pytest

from app.db.repo.quiz_questions_repo import QuizQuestionPoolCandidate

QuestionRecordFactory = Callable[[str], SimpleNamespace | None]


def _fake_record(
    question_id: str,
    *,
    mode_code: str = "QUICK_MIX_A1A2",
    source_file: str = "bank.csv",
    level: str = "A1",
    category: str = "General",
) -> SimpleNamespace:
    return SimpleNamespace(
        question_id=question_id,
        mode_code=mode_code,
        source_file=source_file,
        level=level,
        category=category,
        question_text=f"Frage {question_id}?",
        option_1="A",
        option_2="B",
        option_3="C",
        option_4="D",
        correct_option_id=1,
        correct_answer="B",
        explanation="Erklärung.",
        key=question_id,
        status="ACTIVE",
        quick_mix_eligible=mode_code == "QUICK_MIX_A1A2",
    )


def _install_question_record_repo(
    monkeypatch: pytest.MonkeyPatch,
    records: Mapping[str, SimpleNamespace] | QuestionRecordFactory,
) -> None:
    def record_for(question_id: str) -> SimpleNamespace | None:
        if callable(records):
            return records(question_id)
        return records.get(question_id)

    async def fake_get_by_id(session, question_id):  # noqa: ANN001
        return record_for(question_id)

    async def fake_list_by_ids(session, *, question_ids):  # noqa: ANN001
        return [
            record
            for question_id in question_ids
            if (record := record_for(question_id)) is not None
        ]

    async def fake_list_question_candidates_all_active(  # noqa: ANN001
        session,
        *,
        exclude_question_ids=None,
        preferred_levels=None,
        require_quick_mix_eligible=False,
    ):
        from app.game.questions import runtime_bank

        question_ids = await runtime_bank.QuizQuestionsRepo.list_question_ids_all_active(
            session,
            exclude_question_ids=exclude_question_ids,
            preferred_levels=preferred_levels,
            require_quick_mix_eligible=require_quick_mix_eligible,
        )
        return _candidate_records(question_ids, record_for)

    async def fake_list_question_candidates_for_mode(  # noqa: ANN001
        session,
        *,
        mode_code,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        from app.game.questions import runtime_bank

        question_ids = await runtime_bank.QuizQuestionsRepo.list_question_ids_for_mode(
            session,
            mode_code=mode_code,
            exclude_question_ids=exclude_question_ids,
            preferred_levels=preferred_levels,
        )
        return _candidate_records(question_ids, record_for)

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.get_by_id",
        fake_get_by_id,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_by_ids",
        fake_list_by_ids,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_candidates_all_active",
        fake_list_question_candidates_all_active,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_candidates_for_mode",
        fake_list_question_candidates_for_mode,
    )


def _candidate_records(
    question_ids: list[str],
    record_for: Callable[[str], SimpleNamespace | None],
) -> list[QuizQuestionPoolCandidate]:
    candidates: list[QuizQuestionPoolCandidate] = []
    for question_id in question_ids:
        record = record_for(question_id)
        if record is None:
            candidates.append(
                QuizQuestionPoolCandidate(
                    question_id=question_id,
                    level="A1",
                    source_file="missing.csv",
                    category="Missing",
                )
            )
            continue
        candidates.append(
            QuizQuestionPoolCandidate(
                question_id=record.question_id,
                level=record.level,
                source_file=record.source_file,
                category=record.category,
            )
        )
    return candidates
