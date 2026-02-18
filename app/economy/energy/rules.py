from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

from app.economy.energy.constants import ENERGY_COST_PER_QUIZ
from app.economy.energy.types import EnergyBucketState, EnergySnapshot
from app.economy.energy.time import regen_ticks


def classify_energy_state(snapshot: EnergySnapshot, *, premium_active: bool) -> EnergyBucketState:
    if premium_active:
        return EnergyBucketState.PREMIUM_UNLIMITED
    if snapshot.total_energy == 0:
        return EnergyBucketState.EMPTY
    if snapshot.total_energy <= 3:
        return EnergyBucketState.LOW
    return EnergyBucketState.AVAILABLE


def apply_regen(snapshot: EnergySnapshot, *, now_utc: datetime, premium_active: bool) -> tuple[EnergySnapshot, int]:
    ticks = regen_ticks(snapshot.last_regen_at, now_utc, snapshot.regen_interval_sec)
    if ticks <= 0:
        return snapshot, 0

    updated = replace(
        snapshot,
        last_regen_at=snapshot.last_regen_at + timedelta(seconds=ticks * snapshot.regen_interval_sec),
    )

    if not premium_active:
        updated = replace(
            updated,
            free_energy=min(updated.free_cap, updated.free_energy + ticks),
        )

    return updated, ticks


def apply_daily_topup(snapshot: EnergySnapshot, *, local_date_berlin: date) -> tuple[EnergySnapshot, bool]:
    if local_date_berlin <= snapshot.last_daily_topup_local_date:
        return snapshot, False

    free_energy = snapshot.free_energy
    if free_energy < snapshot.free_cap:
        free_energy = snapshot.free_cap

    return (
        replace(
            snapshot,
            free_energy=free_energy,
            last_daily_topup_local_date=local_date_berlin,
        ),
        True,
    )


def consume_quiz_energy(
    snapshot: EnergySnapshot,
    *,
    premium_active: bool,
) -> tuple[EnergySnapshot, bool, str | None]:
    if premium_active:
        return snapshot, True, "PREMIUM"

    if snapshot.free_energy > 0:
        return replace(snapshot, free_energy=snapshot.free_energy - ENERGY_COST_PER_QUIZ), True, "FREE_ENERGY"

    if snapshot.paid_energy > 0:
        return replace(snapshot, paid_energy=snapshot.paid_energy - ENERGY_COST_PER_QUIZ), True, "PAID_ENERGY"

    return snapshot, False, None


def credit_paid_energy(snapshot: EnergySnapshot, *, amount: int) -> EnergySnapshot:
    return replace(snapshot, paid_energy=snapshot.paid_energy + amount)
