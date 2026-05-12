from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

import app.economy.energy.energy_consume_quiz as energy_consume_quiz
from app.db.models.ledger_entries import LedgerEntry
from app.economy.energy.types import EnergyBucketState
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 4, 24, 8, 0, tzinfo=timezone.utc)


class _Session(AsyncSessionStub):
    def __init__(self) -> None:
        self.flush_count = 0

    async def flush(self, objects=None) -> None:
        del objects
        self.flush_count += 1


def _energy_state(*, free_energy: int, paid_energy: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        free_energy=free_energy,
        paid_energy=paid_energy,
        free_cap=10,
        regen_interval_sec=1800,
        last_regen_at=NOW_UTC,
        last_daily_topup_local_date=NOW_UTC.date(),
        version=0,
        updated_at=NOW_UTC,
    )


@pytest.mark.asyncio
async def test_consume_quiz_debits_free_energy_and_emits_zero_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    state = _energy_state(free_energy=1)
    created_entries: list[LedgerEntry] = []
    zero_events: list[dict[str, Any]] = []

    monkeypatch.setattr(
        energy_consume_quiz,
        "get_or_create_state_for_update",
        _async_return(state),
    )
    monkeypatch.setattr(
        energy_consume_quiz.EntitlementsRepo,
        "has_active_premium",
        _async_return(False),
    )
    monkeypatch.setattr(
        energy_consume_quiz.LedgerRepo,
        "get_by_idempotency_key",
        _async_return(None),
    )

    async def _fake_create(_session, *, entry):
        created_entries.append(entry)
        return entry

    async def _fake_zero_event(_session, **kwargs):
        zero_events.append(kwargs)

    monkeypatch.setattr(energy_consume_quiz.LedgerRepo, "create", _fake_create)
    monkeypatch.setattr(
        energy_consume_quiz,
        "emit_energy_zero_event_if_needed",
        _fake_zero_event,
    )

    result = await energy_consume_quiz.consume_quiz(
        session,
        user_id=11,
        idempotency_key="quiz:consume:test",
        now_utc=NOW_UTC,
    )

    assert result.allowed is True
    assert result.consumed_asset == "FREE_ENERGY"
    assert result.free_energy == 0
    assert result.state == EnergyBucketState.EMPTY
    assert state.free_energy == 0
    assert session.flush_count == 1
    assert len(created_entries) == 1
    entry = cast(LedgerEntry, created_entries[0])
    assert entry.asset == "FREE_ENERGY"
    assert entry.amount == 1
    assert entry.balance_after == 0
    assert zero_events[0]["before_state"] == EnergyBucketState.LOW
    assert zero_events[0]["after_state"] == EnergyBucketState.EMPTY


@pytest.mark.asyncio
async def test_consume_quiz_premium_bypass_does_not_write_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    state = _energy_state(free_energy=0)

    monkeypatch.setattr(
        energy_consume_quiz,
        "get_or_create_state_for_update",
        _async_return(state),
    )
    monkeypatch.setattr(
        energy_consume_quiz.EntitlementsRepo,
        "has_active_premium",
        _async_return(True),
    )
    monkeypatch.setattr(
        energy_consume_quiz.LedgerRepo,
        "get_by_idempotency_key",
        _async_return(None),
    )

    async def _unexpected_create(*_args, **_kwargs):
        pytest.fail("premium bypass should not create a debit ledger entry")

    monkeypatch.setattr(energy_consume_quiz.LedgerRepo, "create", _unexpected_create)

    result = await energy_consume_quiz.consume_quiz(
        session,
        user_id=11,
        idempotency_key="quiz:premium:test",
        now_utc=NOW_UTC,
    )

    assert result.allowed is True
    assert result.premium_bypass is True
    assert result.consumed_asset == "PREMIUM"
    assert result.state == EnergyBucketState.PREMIUM_UNLIMITED
    assert state.free_energy == 0
    assert session.flush_count == 0


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
