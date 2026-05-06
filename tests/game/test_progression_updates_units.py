from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.game.sessions.service import progression_mix_state, progression_updates
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    def __init__(self) -> None:
        self.flush_calls = 0

    async def flush(self, objects: object | None = None) -> None:
        self.flush_calls += 1


@pytest.mark.asyncio
async def test_get_rolling_accuracy_returns_zero_for_empty_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(progression_updates, "recent_attempt_results", _async_return([]))
    assert await progression_updates.get_rolling_accuracy(11, "QUICK_MIX_A1A2", _Session()) == 0.0


@pytest.mark.asyncio
async def test_get_rolling_accuracy_counts_correct_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        progression_updates,
        "recent_attempt_results",
        _async_return([True, False, True, True]),
    )
    assert await progression_updates.get_rolling_accuracy(11, "QUICK_MIX_A1A2", _Session()) == 0.75


@pytest.mark.asyncio
async def test_maybe_activate_mix_step_respects_warmup_and_accuracy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    progress: Any = SimpleNamespace(mix_step=0, correct_in_mix=0, updated_at=None)
    db = _Session()

    current_level, mix_step, correct = await progression_mix_state.maybe_activate_mix_step(
        db,
        progress=progress,
        current_level="A1",
        recent_results=[True] * 10,
        mode="QUICK_MIX_A1A2",
        user_id=11,
        now_utc=NOW_UTC,
        get_rolling_accuracy_fn=_async_return(0.99),
    )
    assert (current_level, mix_step, correct) == ("A1", 0, 0)
    assert db.flush_calls == 0

    current_level, mix_step, correct = await progression_mix_state.maybe_activate_mix_step(
        db,
        progress=progress,
        current_level="A1",
        recent_results=[True] * 30,
        mode="QUICK_MIX_A1A2",
        user_id=11,
        now_utc=NOW_UTC,
        get_rolling_accuracy_fn=_async_return(0.80),
    )
    assert (current_level, mix_step, correct) == ("A1", 1, 0)
    assert progress.mix_step == 1
    assert db.flush_calls == 1


def test_apply_correct_mixed_answer_handles_increment_step_and_promotion() -> None:
    progress: Any = SimpleNamespace(preferred_level="A1", mix_step=1, correct_in_mix=8)
    assert progression_mix_state.apply_correct_mixed_answer(
        progress=progress,
        current_level="A1",
        next_level="A2",
        correct_per_step=10,
    ) == ("A1", 1, 9)

    progress.correct_in_mix = 9
    assert progression_mix_state.apply_correct_mixed_answer(
        progress=progress,
        current_level="A1",
        next_level="A2",
        correct_per_step=10,
    ) == ("A1", 2, 0)

    progress.mix_step = progression_mix_state.MAX_MIX_STEP
    progress.correct_in_mix = 9
    assert progression_mix_state.apply_correct_mixed_answer(
        progress=progress,
        current_level="A1",
        next_level="A2",
        correct_per_step=10,
    ) == ("A2", 0, 0)


@pytest.mark.asyncio
async def test_check_and_advance_resets_terminal_level_and_handles_mixed_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal: Any = SimpleNamespace(
        preferred_level="B2",
        mix_step=2,
        correct_in_mix=3,
        updated_at=None,
    )
    db = _Session()

    monkeypatch.setattr(progression_updates, "load_or_initialize_progress", _async_return(terminal))
    assert await progression_updates.check_and_advance(
        11, "QUICK_MIX_A1A2", db, now_utc=NOW_UTC
    ) == (
        "B2",
        0,
        0,
    )
    assert db.flush_calls == 1

    active: Any = SimpleNamespace(
        preferred_level="A1",
        mix_step=2,
        correct_in_mix=1,
        updated_at=None,
    )
    monkeypatch.setattr(progression_updates, "load_or_initialize_progress", _async_return(active))
    monkeypatch.setattr(progression_updates, "recent_attempt_results", _async_return([False]))
    assert await progression_updates.check_and_advance(
        11, "QUICK_MIX_A1A2", db, now_utc=NOW_UTC
    ) == (
        "A1",
        2,
        1,
    )

    active.correct_in_mix = 9
    monkeypatch.setattr(progression_updates, "recent_attempt_results", _async_return([True]))
    assert await progression_updates.check_and_advance(
        11, "QUICK_MIX_A1A2", db, now_utc=NOW_UTC
    ) == (
        "A1",
        3,
        0,
    )


@pytest.mark.asyncio
async def test_check_and_advance_normalizes_level_and_delegates_to_mix_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    progress: Any = SimpleNamespace(
        preferred_level=" a1 ", mix_step=0, correct_in_mix=0, updated_at=None
    )
    db = _Session()

    monkeypatch.setattr(progression_updates, "load_or_initialize_progress", _async_return(progress))
    monkeypatch.setattr(progression_updates, "recent_attempt_results", _async_return([True] * 5))
    monkeypatch.setattr(
        progression_updates,
        "maybe_activate_mix_step",
        _async_return(("A1", 1, 0)),
    )

    assert await progression_updates.check_and_advance(
        11, "QUICK_MIX_A1A2", db, now_utc=NOW_UTC
    ) == (
        "A1",
        1,
        0,
    )
    assert progress.preferred_level == "A1"


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
