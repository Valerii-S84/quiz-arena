from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.game.sessions.service import progression_mix_state
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    def __init__(self) -> None:
        self.flush_calls = 0

    async def flush(self, objects: object | None = None) -> None:
        self.flush_calls += 1


@pytest.mark.asyncio
async def test_load_or_initialize_progress_returns_existing_or_creates_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing: Any = SimpleNamespace(preferred_level="A2")
    monkeypatch.setattr(
        progression_mix_state.ModeProgressRepo,
        "get_by_user_mode_for_update",
        _async_return(existing),
    )
    assert (
        await progression_mix_state.load_or_initialize_progress(
            _Session(),
            user_id=11,
            mode="QUICK_MIX_A1A2",
            now_utc=NOW_UTC,
        )
        is existing
    )

    created: Any = SimpleNamespace(preferred_level="A1")
    monkeypatch.setattr(
        progression_mix_state.ModeProgressRepo,
        "get_by_user_mode_for_update",
        _async_return(None),
    )
    monkeypatch.setattr(
        progression_mix_state.ModeProgressRepo,
        "upsert_preferred_level",
        _async_return(created),
    )
    assert (
        await progression_mix_state.load_or_initialize_progress(
            _Session(),
            user_id=11,
            mode="QUICK_MIX_A1A2",
            now_utc=NOW_UTC,
        )
        is created
    )


@pytest.mark.asyncio
async def test_reset_terminal_mix_state_is_noop_or_flushes_when_needed() -> None:
    db = _Session()
    progress: Any = SimpleNamespace(mix_step=0, correct_in_mix=0, updated_at=None)
    assert await progression_mix_state.reset_terminal_mix_state(
        db,
        progress=progress,
        current_level="B2",
        now_utc=NOW_UTC,
    ) == ("B2", 0, 0)
    assert db.flush_calls == 0

    progress.mix_step = 2
    progress.correct_in_mix = 1
    assert await progression_mix_state.reset_terminal_mix_state(
        db,
        progress=progress,
        current_level="B2",
        now_utc=NOW_UTC,
    ) == ("B2", 0, 0)
    assert db.flush_calls == 1


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
