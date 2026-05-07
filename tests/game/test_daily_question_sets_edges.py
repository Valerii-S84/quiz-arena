from __future__ import annotations

from datetime import date

import pytest

from app.game.sessions.service import daily_question_sets
from tests.type_helpers import AsyncSessionStub


@pytest.mark.asyncio
async def test_ensure_daily_question_set_returns_existing_slice_without_regeneration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_build(*_args, **_kwargs):
        pytest.fail("full daily set must not be regenerated")

    monkeypatch.setattr(
        daily_question_sets.DailyQuestionSetsRepo,
        "list_question_ids_for_date",
        _async_return(tuple(f"q-{index}" for index in range(1, 10))),
    )
    monkeypatch.setattr(daily_question_sets, "_build_daily_question_ids", _unexpected_build)

    result = await daily_question_sets.ensure_daily_question_set(
        AsyncSessionStub(),
        berlin_date=date(2026, 5, 8),
    )

    assert result == tuple(f"q-{index}" for index in range(1, 8))


@pytest.mark.asyncio
async def test_ensure_daily_question_set_pads_partial_generated_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upserts: list[tuple[str, ...]] = []
    stored_after_upsert = ("q-1", "q-2", "q-3", "q-1", "q-1", "q-1", "q-1")
    list_calls = {"count": 0}

    async def _fake_list(*_args, **_kwargs):
        list_calls["count"] += 1
        return () if list_calls["count"] == 1 else stored_after_upsert

    async def _fake_upsert(*_args, question_ids, **_kwargs):
        upserts.append(tuple(question_ids))

    monkeypatch.setattr(
        daily_question_sets.DailyQuestionSetsRepo,
        "list_question_ids_for_date",
        _fake_list,
    )
    monkeypatch.setattr(
        daily_question_sets,
        "_build_daily_question_ids",
        _async_return(("q-1", "q-2", "q-3")),
    )
    monkeypatch.setattr(
        daily_question_sets.DailyQuestionSetsRepo, "upsert_question_ids", _fake_upsert
    )

    result = await daily_question_sets.ensure_daily_question_set(
        AsyncSessionStub(),
        berlin_date=date(2026, 5, 8),
    )

    assert upserts == [stored_after_upsert]
    assert result == stored_after_upsert


@pytest.mark.asyncio
async def test_ensure_daily_question_set_uses_single_fallback_when_generation_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upserts: list[tuple[str, ...]] = []

    async def _fake_upsert(*_args, question_ids, **_kwargs):
        upserts.append(tuple(question_ids))

    monkeypatch.setattr(
        daily_question_sets.DailyQuestionSetsRepo,
        "list_question_ids_for_date",
        _async_return(()),
    )
    monkeypatch.setattr(daily_question_sets, "_build_daily_question_ids", _async_return(()))
    monkeypatch.setattr(
        daily_question_sets, "_fallback_daily_question_id", _async_return("fallback-q")
    )
    monkeypatch.setattr(
        daily_question_sets.DailyQuestionSetsRepo, "upsert_question_ids", _fake_upsert
    )

    result = await daily_question_sets.ensure_daily_question_set(
        AsyncSessionStub(),
        berlin_date=date(2026, 5, 8),
    )

    assert result == ("fallback-q",) * daily_question_sets.DAILY_CHALLENGE_TOTAL_QUESTIONS
    assert upserts == [result]


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
