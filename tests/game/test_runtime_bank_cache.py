from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_select_question_for_mode_refresh_uses_incremental_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    full_load_calls = 0
    incremental_calls = 0
    monotonic_values = iter([0.0, 0.0, 2.0, 2.0, 2.0, 2.0])

    def fake_monotonic() -> float:
        return next(monotonic_values, 2.0)

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
        nonlocal full_load_calls
        full_load_calls += 1
        return ["q_a", "q_b"]

    async def fake_list_question_pool_changes_since(  # noqa: ANN001
        session,
        *,
        since_updated_at,
    ):
        nonlocal incremental_calls
        del since_updated_at
        incremental_calls += 1
        return [
            SimpleNamespace(
                question_id="q_b",
                mode_code="ARTIKEL_SPRINT",
                level="A1",
                status="DISABLED",
                updated_at=datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                question_id="q_c",
                mode_code="ARTIKEL_SPRINT",
                level="A1",
                status="ACTIVE",
                updated_at=datetime(2026, 2, 20, 10, 1, tzinfo=timezone.utc),
            ),
        ]

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
        "app.game.questions.runtime_bank.QuizQuestionsRepo.list_question_pool_changes_since",
        fake_list_question_pool_changes_since,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank.QuizQuestionsRepo.get_by_id",
        fake_get_by_id,
    )
    monkeypatch.setattr(
        "app.game.questions.runtime_bank_pool.get_settings",
        lambda: SimpleNamespace(quiz_question_pool_cache_ttl_seconds=1),
    )
    monkeypatch.setattr("app.game.questions.runtime_bank_pool.monotonic", fake_monotonic)

    await select_question_for_mode(
        object(),
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 2, 19),
        recent_question_ids=[],
        selection_seed="seed-incremental-refresh",
    )
    second = await select_question_for_mode(
        object(),
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 2, 19),
        recent_question_ids=[],
        selection_seed="seed-incremental-refresh",
    )
    third = await select_question_for_mode(
        object(),
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 2, 19),
        recent_question_ids=[],
        selection_seed="seed-incremental-refresh",
    )

    assert full_load_calls == 1
    assert incremental_calls == 1
    assert second.question_id == third.question_id
    assert second.question_id in {"q_a", "q_c"}
