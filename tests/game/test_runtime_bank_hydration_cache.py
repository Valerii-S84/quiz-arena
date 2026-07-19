from __future__ import annotations

from datetime import date

import pytest

from app.db.repo.quiz_questions_repo import QuizQuestionPoolCandidate
from app.game.questions.runtime_bank import clear_question_pool_cache, select_question_for_mode
from tests.game.runtime_bank_fixtures import _fake_record
from tests.type_helpers import AsyncSessionStub


class _Session(AsyncSessionStub):
    pass


@pytest.fixture(autouse=True)
def clear_runtime_pool_cache() -> None:
    clear_question_pool_cache()


@pytest.mark.asyncio
async def test_select_question_hydrates_from_full_pool_candidate_without_row_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _fake_record("q_full_pool", mode_code="ARTIKEL_SPRINT")

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_candidates_all_active",
        _async_return([]),
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_candidates_for_mode",
        _async_return([_candidate_from_record(record)]),
    )

    async def _unexpected_get_by_id(*_args, **_kwargs):
        pytest.fail("full pool candidates should avoid per-question row lookup")

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.get_by_id",
        _unexpected_get_by_id,
    )

    selected = await select_question_for_mode(
        _Session(),
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 6, 18),
        recent_question_ids=[],
        selection_seed="seed-full-pool",
    )

    assert selected.question_id == "q_full_pool"
    assert selected.text == record.question_text
    assert selected.options == ("A", "B", "C", "D")


@pytest.mark.asyncio
async def test_select_question_falls_back_to_row_hydration_for_lightweight_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _fake_record("q_lightweight", mode_code="ARTIKEL_SPRINT")
    row_lookups: list[str] = []

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_candidates_all_active",
        _async_return([]),
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_candidates_for_mode",
        _async_return(
            [
                QuizQuestionPoolCandidate(
                    question_id=record.question_id,
                    level=record.level,
                    source_file=record.source_file,
                    category=record.category,
                )
            ]
        ),
    )

    async def _get_by_id(_session, question_id):
        row_lookups.append(question_id)
        return record

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.get_by_id",
        _get_by_id,
    )

    selected = await select_question_for_mode(
        _Session(),
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 6, 18),
        recent_question_ids=[],
        selection_seed="seed-lightweight",
    )

    assert selected.question_id == "q_lightweight"
    assert selected.text == record.question_text
    assert row_lookups == ["q_lightweight"]


@pytest.mark.asyncio
async def test_pool_cache_is_separate_by_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    records = {
        "ARTIKEL_SPRINT": _fake_record("q_artikel", mode_code="ARTIKEL_SPRINT"),
        "DAILY_CUP": _fake_record("q_daily", mode_code="DAILY_CUP"),
    }

    async def _candidates_for_mode(_session, *, mode_code, **_kwargs):
        return [_candidate_from_record(records[mode_code])]

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_candidates_all_active",
        _async_return([]),
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_candidates_for_mode",
        _candidates_for_mode,
    )

    first = await select_question_for_mode(
        _Session(),
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 6, 18),
        recent_question_ids=[],
        selection_seed="seed-mode-a",
    )
    second = await select_question_for_mode(
        _Session(),
        "DAILY_CUP",
        local_date_berlin=date(2026, 6, 18),
        recent_question_ids=[],
        selection_seed="seed-mode-b",
    )

    assert first.question_id == "q_artikel"
    assert second.question_id == "q_daily"


def _candidate_from_record(record) -> QuizQuestionPoolCandidate:
    return QuizQuestionPoolCandidate(
        question_id=record.question_id,
        level=record.level,
        source_file=record.source_file,
        category=record.category,
        question_text=record.question_text,
        option_1=record.option_1,
        option_2=record.option_2,
        option_3=record.option_3,
        option_4=record.option_4,
        correct_option_id=record.correct_option_id,
    )


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
