from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.game.sessions.service import progression
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_resolve_start_progression_state_uses_existing_progress_without_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = SimpleNamespace(preferred_level="A2", mix_step=2)

    async def _unexpected_infer(*_args, **_kwargs):
        pytest.fail("existing progress must skip recent-attempt inference")

    monkeypatch.setattr(progression.ModeProgressRepo, "get_by_user_mode", _async_return(existing))
    monkeypatch.setattr(
        progression, "_infer_preferred_level_from_recent_attempt", _unexpected_infer
    )

    level, mix_step, allowed = await progression.resolve_start_progression_state(
        AsyncSessionStub(),
        user_id=11,
        mode_code="QUICK_MIX_A1A2",
        preferred_level_override=None,
        now_utc=NOW_UTC,
    )

    assert (level, mix_step, allowed) == ("A2", 2, ("A2", "B1"))


@pytest.mark.asyncio
async def test_resolve_start_progression_state_initializes_from_inferred_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = SimpleNamespace(preferred_level="B1", mix_step=0)

    monkeypatch.setattr(progression.ModeProgressRepo, "get_by_user_mode", _async_return(None))
    monkeypatch.setattr(
        progression,
        "_infer_preferred_level_from_recent_attempt",
        _async_return("B1"),
    )
    monkeypatch.setattr(
        progression.ModeProgressRepo,
        "upsert_preferred_level",
        _async_return(created),
    )

    level, mix_step, allowed = await progression.resolve_start_progression_state(
        AsyncSessionStub(),
        user_id=11,
        mode_code="QUICK_MIX_A1A2",
        preferred_level_override=None,
        now_utc=NOW_UTC,
    )

    assert (level, mix_step, allowed) == ("B1", 0, ("B1",))


@pytest.mark.asyncio
async def test_resolve_start_progression_state_clamps_override_and_skips_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upsert_calls: list[dict[str, object]] = []

    async def _unexpected_infer(*_args, **_kwargs):
        pytest.fail("explicit override must skip recent-attempt inference")

    async def _fake_upsert(_db, **kwargs):
        upsert_calls.append(kwargs)
        return SimpleNamespace(preferred_level=kwargs["preferred_level"], mix_step=0)

    monkeypatch.setattr(progression.ModeProgressRepo, "get_by_user_mode", _async_return(None))
    monkeypatch.setattr(
        progression, "_infer_preferred_level_from_recent_attempt", _unexpected_infer
    )
    monkeypatch.setattr(progression.ModeProgressRepo, "upsert_preferred_level", _fake_upsert)

    level, mix_step, allowed = await progression.resolve_start_progression_state(
        AsyncSessionStub(),
        user_id=11,
        mode_code="ARTIKEL_SPRINT",
        preferred_level_override="C2",
        now_utc=NOW_UTC,
    )

    assert upsert_calls[0]["preferred_level"] == "B2"
    assert (level, mix_step, allowed) == ("B2", 0, ("B2",))


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
