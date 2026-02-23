from __future__ import annotations

from datetime import date

import pytest

from app.game.questions.runtime_bank import clear_question_pool_cache, select_question_for_mode
from tests.game.runtime_bank_fixtures import _fake_record


@pytest.fixture(autouse=True)
def clear_runtime_pool_cache() -> None:
    clear_question_pool_cache()


@pytest.mark.asyncio
async def test_select_question_for_mode_reuses_cached_pool_between_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    list_calls = 0

    async def fake_list_question_ids_all_active(  # noqa: ANN001
        session,
        *,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        return []

    async def fake_list_question_ids_for_mode(  # noqa: ANN001
        session,
        *,
        mode_code,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        nonlocal list_calls
        list_calls += 1
        return ["q_cache_1", "q_cache_2", "q_cache_3"]

    async def fake_get_by_id(session, question_id):  # noqa: ANN001
        return _fake_record(question_id, mode_code="ARTIKEL_SPRINT")

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_all_active",
        fake_list_question_ids_all_active,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_for_mode",
        fake_list_question_ids_for_mode,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.get_by_id",
        fake_get_by_id,
    )

    first = await select_question_for_mode(
        object(),
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 2, 19),
        recent_question_ids=["q_cache_1"],
        selection_seed="seed-cache-1",
    )
    second = await select_question_for_mode(
        object(),
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 2, 19),
        recent_question_ids=["q_cache_2"],
        selection_seed="seed-cache-2",
    )

    assert first.question_id != "q_cache_1"
    assert second.question_id != "q_cache_2"
    assert list_calls == 1


@pytest.mark.asyncio
async def test_select_question_for_mode_refreshes_stale_cache_if_selected_id_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    list_calls = 0

    async def fake_list_question_ids_all_active(  # noqa: ANN001
        session,
        *,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        return []

    async def fake_list_question_ids_for_mode(  # noqa: ANN001
        session,
        *,
        mode_code,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        nonlocal list_calls
        list_calls += 1
        if list_calls == 1:
            return ["q_stale"]
        return ["q_fresh"]

    async def fake_get_by_id(session, question_id):  # noqa: ANN001
        if question_id == "q_stale":
            return None
        return _fake_record(question_id, mode_code="ARTIKEL_SPRINT")

    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_ids_all_active",
        fake_list_question_ids_all_active,
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
        object(),
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 2, 19),
        recent_question_ids=[],
        selection_seed="seed-stale-refresh",
    )

    assert selected.question_id == "q_fresh"
    assert list_calls == 2
