from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import cast

from app.db.models.energy_state import EnergyState
from app.economy.energy.energy_models import apply_snapshot_to_model, snapshot_from_model

NOW_UTC = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)


def _legacy_energy_state() -> SimpleNamespace:
    return SimpleNamespace(
        free_energy=20,
        paid_energy=0,
        free_cap=20,
        regen_interval_sec=1800,
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
