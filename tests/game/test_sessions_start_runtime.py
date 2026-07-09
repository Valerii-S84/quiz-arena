from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.game.sessions.service import sessions_start_runtime
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_consume_start_energy_keeps_post_lock_ledger_idempotency_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def _fake_consume_quiz(_session, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(allowed=True, free_energy=4, paid_energy=1)

    monkeypatch.setattr(
        sessions_start_runtime.EnergyService,
        "consume_quiz",
        _fake_consume_quiz,
    )

    free_energy, paid_energy, cost = await sessions_start_runtime._consume_start_energy_if_needed(
        AsyncSessionStub(),
        user_id=11,
        source="MENU",
        idempotency_key="menu:start",
        now_utc=NOW_UTC,
    )

    assert (free_energy, paid_energy, cost) == (4, 1, 1)
    assert captured["idempotency_key"] == "energy:menu:start"
    assert "ledger_idempotency_prechecked" not in captured
