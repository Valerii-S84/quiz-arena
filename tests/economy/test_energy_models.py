from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import cast

import pytest

from app.db.models.energy_state import EnergyState
from app.db.repo.energy_repo import EnergyRepo
from app.economy.energy.constants import ENERGY_REGEN_INTERVAL_SEC
from app.economy.energy.energy_models import apply_snapshot_to_model, snapshot_from_model
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)


def _legacy_energy_state() -> SimpleNamespace:
    return SimpleNamespace(
        free_energy=20,
        paid_energy=0,
        free_cap=20,
        regen_interval_sec=ENERGY_REGEN_INTERVAL_SEC,
        last_regen_at=NOW_UTC,
        last_daily_topup_local_date=date(2026, 4, 27),
        updated_at=NOW_UTC,
        version=0,
    )


def test_snapshot_from_model_clamps_legacy_free_energy_cap_to_current_cap() -> None:
    state = cast(EnergyState, _legacy_energy_state())

    snapshot = snapshot_from_model(state)

    assert snapshot.free_energy == 10
    assert snapshot.free_cap == 10


def test_apply_snapshot_to_model_persists_current_free_cap() -> None:
    state = cast(EnergyState, _legacy_energy_state())
    snapshot = snapshot_from_model(state)

    apply_snapshot_to_model(state, snapshot, NOW_UTC)

    assert state.free_energy == 10
    assert state.free_cap == 10


class _Session(AsyncSessionStub):
    def add(self, instance: object, _warn: bool = True) -> None:
        del instance, _warn

    async def flush(self, objects=None) -> None:
        del objects


@pytest.mark.asyncio
async def test_create_default_state_uses_configured_regen_interval() -> None:
    state = await EnergyRepo.create_default_state(
        _Session(),
        user_id=7,
        now_utc=NOW_UTC,
        local_date_berlin=date(2026, 4, 27),
        free_energy_start=10,
        free_energy_cap=10,
        regen_interval_sec=ENERGY_REGEN_INTERVAL_SEC,
    )

    assert state.regen_interval_sec == ENERGY_REGEN_INTERVAL_SEC
