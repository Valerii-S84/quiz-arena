from __future__ import annotations

from datetime import date

import pytest

from app.game.sessions.service.daily_question_sets import _build_daily_question_ids
from tests.game.daily_question_sets_support import (
    DAILY_TEST_LEVELS,
    candidate,
    install_daily_candidate_repo,
)
from tests.type_helpers import AsyncSessionStub


@pytest.mark.asyncio
async def test_daily_question_builder_keeps_preferred_level_window_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = tuple(
        candidate(
            f"level_window_{index}",
            level=level,
            source_file=f"level_source_{index}.csv",
            category=f"level_category_{index}",
        )
        for index, level in enumerate(DAILY_TEST_LEVELS, start=1)
    )
    install_daily_candidate_repo(monkeypatch, candidates)
    selected_by_id = {question.question_id: question for question in candidates}

    selected = await _build_daily_question_ids(AsyncSessionStub(), berlin_date=date(2026, 5, 1))

    assert tuple(selected_by_id[question_id].level for question_id in selected) == DAILY_TEST_LEVELS


@pytest.mark.asyncio
async def test_daily_question_builder_uses_allowed_levels_when_preferred_level_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = tuple(
        candidate(
            f"allowed_level_fallback_{index}",
            level="A1",
            source_file=f"allowed_source_{index}.csv",
            category=f"allowed_category_{index}",
        )
        for index in range(1, 8)
    )
    all_active_calls = install_daily_candidate_repo(monkeypatch, candidates)
    selected_by_id = {question.question_id: question for question in candidates}

    selected = await _build_daily_question_ids(AsyncSessionStub(), berlin_date=date(2026, 5, 4))

    assert len(selected) == 7
    assert tuple(selected_by_id[question_id].level for question_id in selected) == ("A1",) * 7
    assert ("A1", "A2") in all_active_calls
    assert ("A1", "A2", "B1") in all_active_calls


@pytest.mark.asyncio
async def test_daily_question_builder_uses_full_level_chain_when_allowed_window_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = tuple(
        candidate(
            f"chain_level_fallback_{index}",
            level="B1",
            source_file=f"chain_source_{index}.csv",
            category=f"chain_category_{index}",
        )
        for index in range(1, 8)
    )
    install_daily_candidate_repo(monkeypatch, candidates)
    selected_by_id = {question.question_id: question for question in candidates}

    selected = await _build_daily_question_ids(AsyncSessionStub(), berlin_date=date(2026, 5, 5))

    assert len(selected) == 7
    assert tuple(selected_by_id[question_id].level for question_id in selected) == ("B1",) * 7


@pytest.mark.asyncio
async def test_daily_question_builder_duplicates_only_after_unique_candidates_are_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = (
        candidate(
            "tiny_pool_a1",
            level="A1",
            source_file="tiny_a1.csv",
            category="tiny_a1",
        ),
        candidate(
            "tiny_pool_a2",
            level="A2",
            source_file="tiny_a2.csv",
            category="tiny_a2",
        ),
        candidate(
            "tiny_pool_b1",
            level="B1",
            source_file="tiny_b1.csv",
            category="tiny_b1",
        ),
    )
    install_daily_candidate_repo(monkeypatch, candidates)

    selected = await _build_daily_question_ids(AsyncSessionStub(), berlin_date=date(2026, 5, 6))

    assert len(selected) == 7
    assert set(selected) == {question.question_id for question in candidates}
    assert len(set(selected[:3])) == 3
