from __future__ import annotations

from datetime import date

import pytest

from app.game.questions.runtime_bank import (
    clear_question_pool_cache,
    select_friend_challenge_question,
)
from tests.game.runtime_bank_fixtures import _fake_record
from tests.type_helpers import AsyncSessionStub


class _Session(AsyncSessionStub):
    pass


@pytest.fixture(autouse=True)
def clear_runtime_pool_cache() -> None:
    clear_question_pool_cache()


@pytest.mark.asyncio
async def test_friend_challenge_level_fallback_still_prefers_unused_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = {
        "prev_source_a": _fake_record(
            "prev_source_a",
            level="A1",
            source_file="source_a.csv",
            category="Heavy",
        ),
        "same_source_any_level": _fake_record(
            "same_source_any_level",
            level="A1",
            source_file="source_a.csv",
            category="Light",
        ),
        "new_source_any_level": _fake_record(
            "new_source_any_level",
            level="A1",
            source_file="source_b.csv",
            category="Heavy",
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
        if preferred_levels == ("B1",):
            return []
        if preferred_levels is None:
            return ["same_source_any_level", "new_source_any_level"]
        return []

    async def fake_list_question_ids_for_mode(  # noqa: ANN001
        session,
        *,
        mode_code,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        return []

    async def fake_list_by_ids(session, *, question_ids):  # noqa: ANN001
        return [records[question_id] for question_id in question_ids if question_id in records]

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_all_active",
        fake_list_question_ids_all_active,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_for_mode",
        fake_list_question_ids_for_mode,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_by_ids",
        fake_list_by_ids,
    )

    selected = await select_friend_challenge_question(
        _Session(),
        "QUICK_MIX_A1A2",
        local_date_berlin=date(2026, 5, 8),
        previous_round_question_ids=["prev_source_a"],
        selection_seed="friend-level-fallback",
        preferred_level="B1",
    )

    assert selected.question_id == "new_source_any_level"


@pytest.mark.asyncio
async def test_friend_challenge_reuses_source_only_after_unique_questions_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = {
        "prev_source_a": _fake_record("prev_source_a", source_file="source_a.csv"),
        "fresh_same_source": _fake_record("fresh_same_source", source_file="source_a.csv"),
    }

    async def fake_list_question_ids_all_active(  # noqa: ANN001
        session,
        *,
        exclude_question_ids=None,
        preferred_levels=None,
        require_quick_mix_eligible=False,
    ):
        assert require_quick_mix_eligible is True
        return ["fresh_same_source"]

    async def fake_list_question_ids_for_mode(  # noqa: ANN001
        session,
        *,
        mode_code,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        return []

    async def fake_list_by_ids(session, *, question_ids):  # noqa: ANN001
        return [records[question_id] for question_id in question_ids if question_id in records]

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_all_active",
        fake_list_question_ids_all_active,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_for_mode",
        fake_list_question_ids_for_mode,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_by_ids",
        fake_list_by_ids,
    )

    selected = await select_friend_challenge_question(
        _Session(),
        "QUICK_MIX_A1A2",
        local_date_berlin=date(2026, 5, 8),
        previous_round_question_ids=["prev_source_a"],
        selection_seed="friend-source-exhausted",
        preferred_level="A1",
    )

    assert selected.question_id == "fresh_same_source"
