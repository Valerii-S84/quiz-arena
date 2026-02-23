from __future__ import annotations

from datetime import datetime

from app.economy.energy.rules import apply_regen
from app.economy.energy.types import EnergySnapshot


def apply_regen_tick(
    snapshot: EnergySnapshot, *, now_utc: datetime, premium_active: bool
) -> tuple[EnergySnapshot, int]:
    return apply_regen(snapshot, now_utc=now_utc, premium_active=premium_active)
