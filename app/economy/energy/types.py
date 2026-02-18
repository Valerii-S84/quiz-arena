from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class EnergyBucketState(str, Enum):
    PREMIUM_UNLIMITED = "E_PREMIUM_UNLIMITED"
    AVAILABLE = "E_AVAILABLE"
    LOW = "E_LOW"
    EMPTY = "E_EMPTY"


@dataclass(slots=True)
class EnergySnapshot:
    free_energy: int
    paid_energy: int
    free_cap: int
    regen_interval_sec: int
    last_regen_at: datetime
    last_daily_topup_local_date: date

    @property
    def total_energy(self) -> int:
        return self.free_energy + self.paid_energy


@dataclass(slots=True)
class EnergyConsumeResult:
    allowed: bool
    idempotent_replay: bool
    premium_bypass: bool
    consumed_asset: str | None
    free_energy: int
    paid_energy: int
    state: EnergyBucketState


@dataclass(slots=True)
class EnergyCreditResult:
    amount: int
    idempotent_replay: bool
    free_energy: int
    paid_energy: int
    state: EnergyBucketState
