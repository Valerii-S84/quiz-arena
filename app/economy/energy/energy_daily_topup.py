from __future__ import annotations

from datetime import datetime

from app.economy.energy.rules import apply_daily_topup
from app.economy.energy.time import berlin_local_date
from app.economy.energy.types import EnergySnapshot


def apply_daily_topup_berlin(
    snapshot: EnergySnapshot, *, now_utc: datetime
) -> tuple[EnergySnapshot, bool]:
    return apply_daily_topup(snapshot, local_date_berlin=berlin_local_date(now_utc))
