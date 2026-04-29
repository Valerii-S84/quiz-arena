from __future__ import annotations

from datetime import date

import pytest

from app.game.questions.runtime_bank import clear_question_pool_cache, select_question_for_mode
from tests.game.runtime_bank_fixtures import _fake_record, _install_question_record_repo
from tests.type_helpers import AsyncSessionStub


class _Session(AsyncSessionStub):
    pass


@pytest.fixture(autouse=True)
def clear_runtime_pool_cache() -> None:
    clear_question_pool_cache()


@pytest.mark.asyncio
async def test_quick_mix_prefers_unused_source_file_after_recent_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = {
        "recent_same_source": _fake_record(
            "recent_same_source",
            source_file="source_a.csv",
            category="Shared",
        ),
        "same_source_fresh": _fake_record(
            "same_source_fresh",
            source_file="source_a.csv",
            category="Other",
        ),
        "new_source_fresh": _fake_record(
            "new_source_fresh",
            source_file="source_b.csv",
            category="Shared",
        ),
    }

    async def fake_list_question_ids_all_active(  # noqa: ANN001
        session,
        *,
        exclude_question_ids=None,
        preferred_levels=None,
        require_quick_mix_eligible=False,
    ):
        assert require_quick_mix_eligible is True
        return ["same_source_fresh", "new_source_fresh"]

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_all_active",
        fake_list_question_ids_all_active,
    )
    _install_question_record_repo(monkeypatch, records)

    selected = await select_question_for_mode(
        _Session(),
        "QUICK_MIX_A1A2",
        local_date_berlin=date(2026, 5, 7),
        recent_question_ids=["recent_same_source"],
        selection_seed="seed-1",
    )

    assert selected.question_id == "new_source_fresh"


@pytest.mark.asyncio
async def test_quick_mix_falls_back_to_unused_category_when_source_repeats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = {
        "recent_heavy": _fake_record(
            "recent_heavy",
            source_file="shared_source.csv",
            category="Heavy",
        ),
        "fresh_heavy": _fake_record(
            "fresh_heavy",
            source_file="shared_source.csv",
            category="Heavy",
        ),
        "fresh_light": _fake_record(
            "fresh_light",
            source_file="shared_source.csv",
            category="Light",
        ),
    }

    async def fake_list_question_ids_all_active(  # noqa: ANN001
        session,
        *,
        exclude_question_ids=None,
        preferred_levels=None,
        require_quick_mix_eligible=False,
    ):
        assert require_quick_mix_eligible is True
        return ["fresh_heavy", "fresh_light"]

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_all_active",
        fake_list_question_ids_all_active,
    )
    _install_question_record_repo(monkeypatch, records)

    selected = await select_question_for_mode(
        _Session(),
        "QUICK_MIX_A1A2",
        local_date_berlin=date(2026, 5, 7),
        recent_question_ids=["recent_heavy"],
        selection_seed="seed-category-fallback",
    )

    assert selected.question_id == "fresh_light"
