from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast

import pytest

import app.economy.energy.energy_consume as energy_consume
from app.db.models.ledger_entries import LedgerEntry
from app.economy.energy.types import EnergyBucketState
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 4, 24, 8, 0, tzinfo=timezone.utc)


class _Session(AsyncSessionStub):
    async def flush(self, objects=None) -> None:
        del objects
        return None


def _energy_state(*, free_energy: int, free_cap: int) -> SimpleNamespace:
    return SimpleNamespace(
        free_energy=free_energy,
        paid_energy=0,
        free_cap=free_cap,
        regen_interval_sec=1800,
        last_regen_at=NOW_UTC,
        last_daily_topup_local_date=NOW_UTC.date(),
        version=0,
        updated_at=NOW_UTC,
    )


@pytest.mark.asyncio
async def test_credit_free_energy_caps_to_current_free_cap_and_logs_actual_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    state = _energy_state(free_energy=10, free_cap=12)
    created_entries: list[LedgerEntry] = []

    monkeypatch.setattr(energy_consume, "get_or_create_state_for_update", _async_return(state))
    monkeypatch.setattr(
        energy_consume.EntitlementsRepo,
        "has_active_premium",
        _async_return(False),
    )
    monkeypatch.setattr(
        energy_consume.LedgerRepo,
        "get_by_idempotency_key",
        _async_return(None),
    )

    async def _fake_create(_session, *, entry):
        created_entries.append(entry)
        return entry

    monkeypatch.setattr(energy_consume.LedgerRepo, "create", _fake_create)

    result = await energy_consume.credit_free_energy(
        session,
        user_id=11,
        amount=3,
        idempotency_key="daily:reward:energy:test",
        now_utc=NOW_UTC,
        source="DAILY_CHALLENGE",
    )

    assert result.amount == 2
    assert result.idempotent_replay is False
    assert result.free_energy == 12
    assert result.paid_energy == 0
    assert result.state == EnergyBucketState.AVAILABLE
    assert state.free_energy == 12
    assert len(created_entries) == 1
    entry = cast(LedgerEntry, created_entries[0])
    assert entry.amount == 2
    assert entry.balance_after == 12
    assert entry.asset == "FREE_ENERGY"


@pytest.mark.asyncio
async def test_credit_free_energy_adds_nothing_when_already_at_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    state = _energy_state(free_energy=12, free_cap=12)

    monkeypatch.setattr(energy_consume, "get_or_create_state_for_update", _async_return(state))
    monkeypatch.setattr(
        energy_consume.EntitlementsRepo,
        "has_active_premium",
        _async_return(False),
    )
    monkeypatch.setattr(
        energy_consume.LedgerRepo,
        "get_by_idempotency_key",
        _async_return(None),
    )

    async def _unexpected_create(*_args, **_kwargs):
        pytest.fail("ledger entry should not be created when free energy is already capped")

    monkeypatch.setattr(energy_consume.LedgerRepo, "create", _unexpected_create)

    result = await energy_consume.credit_free_energy(
        session,
        user_id=11,
        amount=3,
        idempotency_key="daily:reward:energy:at-cap",
        now_utc=NOW_UTC,
        source="DAILY_CHALLENGE",
    )

    assert result.amount == 0
    assert result.idempotent_replay is False
    assert result.free_energy == 12
    assert result.state == EnergyBucketState.AVAILABLE
    assert state.free_energy == 12


@pytest.mark.asyncio
async def test_credit_free_energy_replay_is_idempotent_and_does_not_duplicate_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    state = _energy_state(free_energy=12, free_cap=12)
    existing_entry = SimpleNamespace(amount=2)

    monkeypatch.setattr(energy_consume, "get_or_create_state_for_update", _async_return(state))
    monkeypatch.setattr(
        energy_consume.EntitlementsRepo,
        "has_active_premium",
        _async_return(False),
    )
    monkeypatch.setattr(
        energy_consume.LedgerRepo,
        "get_by_idempotency_key",
        _async_return(existing_entry),
    )

    async def _unexpected_create(*_args, **_kwargs):
        pytest.fail("ledger entry should not be duplicated on idempotent replay")

    monkeypatch.setattr(energy_consume.LedgerRepo, "create", _unexpected_create)

    result = await energy_consume.credit_free_energy(
        session,
        user_id=11,
        amount=3,
        idempotency_key="daily:reward:energy:replay",
        now_utc=NOW_UTC,
        source="DAILY_CHALLENGE",
    )

    assert result.amount == 2
    assert result.idempotent_replay is True
    assert result.free_energy == 12
    assert state.free_energy == 12


@pytest.mark.asyncio
async def test_credit_paid_energy_grants_full_reward_without_free_cap_clamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    state = _energy_state(free_energy=18, free_cap=20)
    created_entries: list[LedgerEntry] = []

    monkeypatch.setattr(energy_consume, "get_or_create_state_for_update", _async_return(state))
    monkeypatch.setattr(
        energy_consume.EntitlementsRepo,
        "has_active_premium",
        _async_return(False),
    )
    monkeypatch.setattr(
        energy_consume.LedgerRepo,
        "get_by_idempotency_key",
        _async_return(None),
    )

    async def _fake_create(_session, *, entry):
        created_entries.append(entry)
        return entry

    monkeypatch.setattr(energy_consume.LedgerRepo, "create", _fake_create)

    result = await energy_consume.credit_paid_energy(
        session,
        user_id=11,
        amount=5,
        idempotency_key="daily:cup:reward:energy:test",
        now_utc=NOW_UTC,
        source="TOURNAMENT",
    )

    assert result.amount == 5
    assert result.idempotent_replay is False
    assert result.free_energy == 18
    assert result.paid_energy == 5
    assert result.state == EnergyBucketState.AVAILABLE
    assert state.free_energy == 18
    assert state.paid_energy == 5
    assert len(created_entries) == 1
    entry = cast(LedgerEntry, created_entries[0])
    assert entry.amount == 5
    assert entry.balance_after == 5
    assert entry.asset == "PAID_ENERGY"
    assert entry.source == "TOURNAMENT"


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
