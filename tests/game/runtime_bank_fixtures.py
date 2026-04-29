from __future__ import annotations

from collections.abc import Callable, Mapping
from types import SimpleNamespace

import pytest

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

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.get_by_id",
        fake_get_by_id,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_by_ids",
        fake_list_by_ids,
    )
