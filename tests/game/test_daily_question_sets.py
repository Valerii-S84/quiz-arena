from __future__ import annotations

from datetime import date

import pytest

from app.game.sessions.service.daily_question_sets import (
    _build_daily_question_ids,
    daily_level_window_for_position,
    is_daily_level_allowed_for_position,
)
from tests.game.daily_question_sets_support import (
    DAILY_TEST_LEVELS,
    candidate,
    install_daily_candidate_repo,
)
from tests.type_helpers import AsyncSessionStub


def test_daily_level_window_matches_expected_sequence() -> None:
    expected_preferred = ("A1", "A1", "A2", "A2", "A2", "B1", "B1")
    observed = tuple(daily_level_window_for_position(position)[0] for position in range(1, 8))
    assert observed == expected_preferred


def test_daily_level_window_caps_allowed_levels_by_position() -> None:
    assert is_daily_level_allowed_for_position(position=1, level="A1") is True
    assert is_daily_level_allowed_for_position(position=1, level="A2") is False
    assert is_daily_level_allowed_for_position(position=5, level="A2") is True
    assert is_daily_level_allowed_for_position(position=5, level="B1") is False
    assert is_daily_level_allowed_for_position(position=6, level="B1") is True


@pytest.mark.asyncio
async def test_daily_question_builder_prefers_unused_source_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = tuple(
        candidate(
            f"source_diverse_{index}",
            level=level,
            source_file=f"source_{index}.csv",
            category=f"category_{index}",
        )
        for index, level in enumerate(DAILY_TEST_LEVELS, start=1)
    )
    install_daily_candidate_repo(monkeypatch, candidates)
    selected_by_id = {candidate.question_id: candidate for candidate in candidates}

    selected = await _build_daily_question_ids(AsyncSessionStub(), berlin_date=date(2026, 4, 29))

    assert len(selected) == 7
    assert len({selected_by_id[question_id].source_file for question_id in selected}) == 7


@pytest.mark.asyncio
async def test_daily_question_builder_falls_back_when_source_files_are_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = tuple(
        candidate(
            f"limited_source_{index}",
            level=level,
            source_file="shared_source.csv",
            category=f"category_{index % 3}",
        )
        for index, level in enumerate(DAILY_TEST_LEVELS, start=1)
    )
    install_daily_candidate_repo(monkeypatch, candidates)

    selected = await _build_daily_question_ids(AsyncSessionStub(), berlin_date=date(2026, 4, 30))

    assert len(selected) == 7
    assert len(set(selected)) == 7


@pytest.mark.asyncio
async def test_daily_question_builder_prefers_unused_categories_after_source_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = tuple(
        candidate(
            f"category_fallback_{index}",
            level=level,
            source_file="shared_source.csv",
            category=f"distinct_category_{index}",
        )
        for index, level in enumerate(DAILY_TEST_LEVELS, start=1)
    )
    install_daily_candidate_repo(monkeypatch, candidates)
    selected_by_id = {candidate.question_id: candidate for candidate in candidates}

    selected = await _build_daily_question_ids(AsyncSessionStub(), berlin_date=date(2026, 5, 3))

    assert len(selected) == 7
    assert {selected_by_id[question_id].source_file for question_id in selected} == {
        "shared_source.csv"
    }
    assert len({selected_by_id[question_id].category for question_id in selected}) == 7


@pytest.mark.asyncio
async def test_daily_question_builder_uses_quick_mix_eligible_candidate_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = tuple(
        candidate(
            f"quick_mix_semantics_{index}",
            level=level,
            source_file=f"quick_mix_source_{index}.csv",
            category=f"quick_mix_category_{index}",
        )
        for index, level in enumerate(DAILY_TEST_LEVELS, start=1)
    )
    all_active_calls = install_daily_candidate_repo(monkeypatch, candidates)

    selected = await _build_daily_question_ids(AsyncSessionStub(), berlin_date=date(2026, 5, 2))

    assert len(selected) == 7
    assert all_active_calls
