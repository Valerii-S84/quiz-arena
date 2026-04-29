from __future__ import annotations

from datetime import date

import pytest

from app.game.questions.runtime_bank import clear_question_pool_cache, select_question_for_mode
from tests.game.runtime_bank_fixtures import _fake_record
from tests.type_helpers import AsyncSessionStub


class _Session(AsyncSessionStub):
    pass


@pytest.fixture(autouse=True)
def clear_runtime_pool_cache() -> None:
    clear_question_pool_cache()


@pytest.mark.asyncio
async def test_non_quick_mix_mode_prefers_unused_source_file_after_recent_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = {
        "recent_same_source": _fake_record(
            "recent_same_source",
            mode_code="ARTIKEL_SPRINT",
            source_file="artikel_a.csv",
            category="Shared",
        ),
        "same_source_fresh": _fake_record(
            "same_source_fresh",
            mode_code="ARTIKEL_SPRINT",
            source_file="artikel_a.csv",
            category="Other",
        ),
        "new_source_fresh": _fake_record(
            "new_source_fresh",
            mode_code="ARTIKEL_SPRINT",
            source_file="artikel_b.csv",
            category="Shared",
        ),
    }

    async def fail_list_question_ids_all_active(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("Non-Quick Mix mode must use mode-scoped pool")

    async def fake_list_question_ids_for_mode(  # noqa: ANN001
        session,
        *,
        mode_code,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        assert mode_code == "ARTIKEL_SPRINT"
        return ["same_source_fresh", "new_source_fresh"]

    async def fake_get_by_id(session, question_id):  # noqa: ANN001
        return records.get(question_id)

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_all_active",
        fail_list_question_ids_all_active,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_for_mode",
        fake_list_question_ids_for_mode,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.get_by_id",
        fake_get_by_id,
    )

    selected = await select_question_for_mode(
        _Session(),
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 5, 8),
        recent_question_ids=["recent_same_source"],
        selection_seed="seed-1",
    )

    assert selected.question_id == "new_source_fresh"


@pytest.mark.asyncio
async def test_quick_mix_allows_duplicate_only_when_unique_candidates_are_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = {
        "recent_a": _fake_record("recent_a", source_file="source_a.csv", category="A"),
        "recent_b": _fake_record("recent_b", source_file="source_b.csv", category="B"),
    }

    async def fake_list_question_ids_all_active(  # noqa: ANN001
        session,
        *,
        exclude_question_ids=None,
        preferred_levels=None,
        require_quick_mix_eligible=False,
    ):
        assert require_quick_mix_eligible is True
        return ["recent_a", "recent_b"]

    async def fake_get_by_id(session, question_id):  # noqa: ANN001
        return records.get(question_id)

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_all_active",
        fake_list_question_ids_all_active,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.get_by_id",
        fake_get_by_id,
    )

    selected = await select_question_for_mode(
        _Session(),
        "QUICK_MIX_A1A2",
        local_date_berlin=date(2026, 5, 8),
        recent_question_ids=["recent_a", "recent_b"],
        selection_seed="seed-duplicate-fallback",
    )

    assert selected.question_id in {"recent_a", "recent_b"}
