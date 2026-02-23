from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.economy.energy.rules import (
    apply_daily_topup,
    apply_regen,
    classify_energy_state,
    consume_quiz_energy,
    credit_paid_energy,
)
from app.economy.energy.time import berlin_local_date, regen_ticks
from app.economy.energy.types import EnergyBucketState, EnergySnapshot

UTC = timezone.utc


def snapshot(
    *,
    free_energy: int,
    paid_energy: int,
    last_regen_at: datetime | None = None,
    last_daily_topup_local_date: date = date(2026, 2, 17),
) -> EnergySnapshot:
    return EnergySnapshot(
        free_energy=free_energy,
        paid_energy=paid_energy,
        free_cap=20,
        regen_interval_sec=1800,
        last_regen_at=last_regen_at or datetime(2026, 2, 17, 12, 0, tzinfo=UTC),
        last_daily_topup_local_date=last_daily_topup_local_date,
    )


def test_classify_premium_unlimited() -> None:
    state = classify_energy_state(snapshot(free_energy=0, paid_energy=0), premium_active=True)
    assert state == EnergyBucketState.PREMIUM_UNLIMITED


def test_transition_available_to_available_on_consume() -> None:
    state_before = snapshot(free_energy=5, paid_energy=0)
    state_after, allowed, asset = consume_quiz_energy(state_before, premium_active=False)

    assert allowed is True
    assert asset == "FREE_ENERGY"
    assert classify_energy_state(state_after, premium_active=False) == EnergyBucketState.AVAILABLE


def test_transition_available_to_low_on_consume() -> None:
    state_before = snapshot(free_energy=4, paid_energy=0)
    state_after, allowed, _ = consume_quiz_energy(state_before, premium_active=False)

    assert allowed is True
    assert classify_energy_state(state_after, premium_active=False) == EnergyBucketState.LOW


def test_transition_low_to_low_on_consume() -> None:
    state_before = snapshot(free_energy=2, paid_energy=0)
    state_after, allowed, _ = consume_quiz_energy(state_before, premium_active=False)

    assert allowed is True
    assert classify_energy_state(state_after, premium_active=False) == EnergyBucketState.LOW


def test_transition_low_to_empty_on_consume() -> None:
    state_before = snapshot(free_energy=1, paid_energy=0)
    state_after, allowed, _ = consume_quiz_energy(state_before, premium_active=False)

    assert allowed is True
    assert classify_energy_state(state_after, premium_active=False) == EnergyBucketState.EMPTY


def test_transition_empty_to_low_on_regen_tick() -> None:
    now_utc = datetime(2026, 2, 17, 13, 0, tzinfo=UTC)
    state_before = snapshot(
        free_energy=0, paid_energy=0, last_regen_at=now_utc - timedelta(minutes=30)
    )

    state_after, ticks = apply_regen(state_before, now_utc=now_utc, premium_active=False)

    assert ticks == 1
    assert state_after.free_energy == 1
    assert classify_energy_state(state_after, premium_active=False) == EnergyBucketState.LOW


def test_transition_empty_to_available_on_paid_credit() -> None:
    state_before = snapshot(free_energy=0, paid_energy=0)
    state_after = credit_paid_energy(state_before, amount=10)

    assert state_after.paid_energy == 10
    assert classify_energy_state(state_after, premium_active=False) == EnergyBucketState.AVAILABLE


def test_transition_low_to_available_on_regen_tick() -> None:
    now_utc = datetime(2026, 2, 17, 13, 0, tzinfo=UTC)
    state_before = snapshot(
        free_energy=3, paid_energy=0, last_regen_at=now_utc - timedelta(minutes=30)
    )

    state_after, ticks = apply_regen(state_before, now_utc=now_utc, premium_active=False)

    assert ticks == 1
    assert state_after.free_energy == 4
    assert classify_energy_state(state_after, premium_active=False) == EnergyBucketState.AVAILABLE


def test_transition_to_available_on_daily_topup() -> None:
    state_before = snapshot(
        free_energy=2,
        paid_energy=0,
        last_daily_topup_local_date=date(2026, 2, 16),
    )

    state_after, applied = apply_daily_topup(state_before, local_date_berlin=date(2026, 2, 17))

    assert applied is True
    assert state_after.free_energy == 20
    assert classify_energy_state(state_after, premium_active=False) == EnergyBucketState.AVAILABLE


@pytest.mark.parametrize(
    ("free_energy", "paid_energy", "expected"),
    [
        (0, 0, EnergyBucketState.EMPTY),
        (1, 0, EnergyBucketState.LOW),
        (4, 0, EnergyBucketState.AVAILABLE),
    ],
)
def test_transition_premium_off_recomputes_state(
    free_energy: int,
    paid_energy: int,
    expected: EnergyBucketState,
) -> None:
    state = snapshot(free_energy=free_energy, paid_energy=paid_energy)
    assert classify_energy_state(state, premium_active=False) == expected


def test_no_negative_energy_on_consume_when_empty() -> None:
    state_before = snapshot(free_energy=0, paid_energy=0)
    state_after, allowed, asset = consume_quiz_energy(state_before, premium_active=False)

    assert allowed is False
    assert asset is None
    assert state_after.free_energy == 0
    assert state_after.paid_energy == 0


def test_regen_uses_elapsed_full_ticks_only() -> None:
    last_regen = datetime(2026, 2, 17, 12, 0, tzinfo=UTC)
    now_utc = last_regen + timedelta(minutes=89)

    assert regen_ticks(last_regen, now_utc, 1800) == 2


def test_regen_does_not_increase_free_energy_when_premium_active() -> None:
    now_utc = datetime(2026, 2, 17, 13, 0, tzinfo=UTC)
    state_before = snapshot(
        free_energy=10, paid_energy=5, last_regen_at=now_utc - timedelta(hours=2)
    )

    state_after, ticks = apply_regen(state_before, now_utc=now_utc, premium_active=True)

    assert ticks == 4
    assert state_after.free_energy == 10
    assert state_after.last_regen_at == now_utc


def test_berlin_local_date_boundary_in_utc() -> None:
    assert berlin_local_date(datetime(2026, 3, 28, 23, 30, tzinfo=UTC)) == date(2026, 3, 29)
    assert berlin_local_date(datetime(2026, 3, 29, 22, 30, tzinfo=UTC)) == date(2026, 3, 30)
