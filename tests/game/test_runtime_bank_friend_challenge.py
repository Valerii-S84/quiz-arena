from __future__ import annotations

from datetime import date

import pytest

from app.game.questions.runtime_bank import clear_question_pool_cache, select_friend_challenge_question
from tests.game.runtime_bank_fixtures import _fake_record


@pytest.fixture(autouse=True)
def clear_runtime_pool_cache() -> None:
    clear_question_pool_cache()


@pytest.mark.asyncio
async def test_select_friend_challenge_question_prefers_less_used_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = {
        "q_a2_heavy": _fake_record("q_a2_heavy", level="A2", category="Heavy"),
        "q_a2_light": _fake_record("q_a2_light", level="A2", category="Light"),
        "prev_1": _fake_record("prev_1", level="A1", category="Heavy"),
        "prev_2": _fake_record("prev_2", level="A1", category="Heavy"),
    }

    async def fake_list_question_ids_all_active(  # noqa: ANN001
        session,
        *,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        if preferred_levels == ("A2",):
            return ["q_a2_heavy", "q_a2_light"]
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
        return [records[qid] for qid in question_ids if qid in records]

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
        object(),
        "QUICK_MIX_A1A2",
        local_date_berlin=date(2026, 2, 19),
        previous_round_question_ids=["prev_1", "prev_2"],
        selection_seed="seed-category-balance",
        preferred_level="A2",
    )

    assert selected.question_id == "q_a2_light"
