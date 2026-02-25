from __future__ import annotations

from datetime import date

import pytest

from app.game.questions.runtime_bank import clear_question_pool_cache, select_question_for_mode
from tests.game.runtime_bank_fixtures import _fake_record


@pytest.fixture(autouse=True)
def clear_runtime_pool_cache() -> None:
    clear_question_pool_cache()


@pytest.mark.asyncio
async def test_select_question_for_mode_uses_db_pool_before_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        if exclude_question_ids:
            return ["db_q1"]
        return ["db_q1"]

    async def fake_get_by_id(session, question_id):  # noqa: ANN001
        return _fake_record(question_id)

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
        object(),  # session is unused by monkeypatched repo methods
        "ARTIKEL_SPRINT",
        local_date_berlin=date(2026, 2, 19),
        recent_question_ids=["recent_q"],
        selection_seed="seed-1",
    )
    assert selected.question_id == "db_q1"
    assert selected.correct_option == 1


@pytest.mark.asyncio
async def test_select_question_for_mode_daily_uses_quick_mix_source_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_all_active = 0
    called_for_mode: list[str] = []

    async def fake_list_question_ids_all_active(  # noqa: ANN001
        session,
        *,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        nonlocal called_all_active
        called_all_active += 1
        return ["q_a", "q_b"]

    async def fake_list_question_ids_for_mode(  # noqa: ANN001
        session,
        *,
        mode_code,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        called_for_mode.append(mode_code)
        del exclude_question_ids, preferred_levels
        if mode_code == "QUICK_MIX_A1A2":
            return ["q_a", "q_b"]
        return []

    async def fake_get_by_id(session, question_id):  # noqa: ANN001
        return _fake_record(question_id)

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
        "DAILY_CHALLENGE",
        local_date_berlin=date(2026, 2, 19),
        recent_question_ids=["ignored_recent"],
        selection_seed="seed-ignored",
    )
    second = await select_question_for_mode(
        object(),
        "DAILY_CHALLENGE",
        local_date_berlin=date(2026, 2, 19),
        recent_question_ids=["another_recent"],
        selection_seed="another-seed",
    )

    assert first.question_id == second.question_id
    assert called_all_active == 0
    assert called_for_mode == ["QUICK_MIX_A1A2"]


@pytest.mark.asyncio
async def test_select_question_for_quick_mix_uses_mode_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_all_active = 0
    called_for_mode = 0

    async def fake_list_question_ids_all_active(  # noqa: ANN001
        session,
        *,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        nonlocal called_all_active
        called_all_active += 1
        return ["mix_q_1"]

    async def fake_list_question_ids_for_mode(  # noqa: ANN001
        session,
        *,
        mode_code,
        exclude_question_ids=None,
        preferred_levels=None,
    ):
        nonlocal called_for_mode
        called_for_mode += 1
        return ["mode_q_1"]

    async def fake_get_by_id(session, question_id):  # noqa: ANN001
        return _fake_record(question_id)

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
        "QUICK_MIX_A1A2",
        local_date_berlin=date(2026, 2, 19),
        recent_question_ids=[],
        selection_seed="seed-mix",
    )
    assert selected.question_id == "mode_q_1"
    assert called_all_active == 0
    assert called_for_mode > 0


@pytest.mark.asyncio
async def test_select_question_for_mode_prefers_requested_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_levels: list[tuple[str, ...] | None] = []

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
        recorded_levels.append(tuple(preferred_levels) if preferred_levels else None)
        if preferred_levels == ("B1",):
            return ["q_b1"]
        return ["q_default"]

    async def fake_get_by_id(session, question_id):  # noqa: ANN001
        level = "B1" if question_id == "q_b1" else "A1"
        record = _fake_record(question_id, mode_code="ARTIKEL_SPRINT")
        record.level = level
        return record

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
        selection_seed="seed-level",
        preferred_level="B1",
    )
    assert selected.question_id == "q_b1"
    assert ("B1",) in recorded_levels


@pytest.mark.asyncio
async def test_select_question_for_mode_falls_back_to_next_level_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_levels: list[tuple[str, ...] | None] = []

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
        recorded_levels.append(tuple(preferred_levels) if preferred_levels else None)
        del session, mode_code, exclude_question_ids
        if preferred_levels == ("B1",):
            return []
        if preferred_levels == ("B2",):
            return ["q_b2"]
        return ["q_default"]

    async def fake_get_by_id(session, question_id):  # noqa: ANN001
        level = "B2" if question_id == "q_b2" else "A1"
        record = _fake_record(question_id, mode_code="ARTIKEL_SPRINT")
        record.level = level
        return record

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
        selection_seed="seed-level-fallback",
        preferred_level="B1",
    )
    assert selected.question_id == "q_b2"
    assert ("B1",) in recorded_levels
    assert ("B2",) in recorded_levels
    assert None not in recorded_levels
