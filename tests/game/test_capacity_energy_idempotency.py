from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

import app.economy.energy.energy_consume_quiz as energy_consume_quiz
from app.db.models.ledger_entries import LedgerEntry
from app.economy.energy.constants import ENERGY_REGEN_INTERVAL_SEC
from app.economy.energy.types import EnergyBucketState
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    def __init__(self) -> None:
        self.flush_count = 0

    async def flush(self, objects=None) -> None:
        del objects
        self.flush_count += 1


def _energy_state(
    *,
    free_energy: int,
    paid_energy: int = 0,
    last_regen_at: datetime = NOW_UTC,
    last_daily_topup_local_date: date | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        free_energy=free_energy,
        paid_energy=paid_energy,
        free_cap=10,
        regen_interval_sec=ENERGY_REGEN_INTERVAL_SEC,
        last_regen_at=last_regen_at,
        last_daily_topup_local_date=last_daily_topup_local_date or NOW_UTC.date(),
        version=0,
        updated_at=NOW_UTC,
    )


@pytest.mark.asyncio
async def test_consume_quiz_denies_no_energy_without_negative_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    state = _energy_state(free_energy=0, paid_energy=0)

    monkeypatch.setattr(
        energy_consume_quiz,
        "get_or_create_state_and_premium_status_for_update",
        _state_and_premium(state, premium_active=False),
    )
    monkeypatch.setattr(
        energy_consume_quiz.LedgerRepo, "get_by_idempotency_key", _async_return(None)
    )

    async def _unexpected_create(*_args, **_kwargs):
        pytest.fail("blocked energy consume must not create a ledger row")

    monkeypatch.setattr(energy_consume_quiz.LedgerRepo, "create", _unexpected_create)

    result = await energy_consume_quiz.consume_quiz(
        session,
        user_id=11,
        idempotency_key="energy:no-balance",
        now_utc=NOW_UTC,
    )

    assert result.allowed is False
    assert result.state == EnergyBucketState.EMPTY
    assert (state.free_energy, state.paid_energy) == (0, 0)
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_consume_quiz_regenerates_before_debit(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _Session()
    state = _energy_state(
        free_energy=0,
        last_regen_at=NOW_UTC - timedelta(seconds=ENERGY_REGEN_INTERVAL_SEC),
    )
    created_entries: list[LedgerEntry] = []

    monkeypatch.setattr(
        energy_consume_quiz,
        "get_or_create_state_and_premium_status_for_update",
        _state_and_premium(state, premium_active=False),
    )
    monkeypatch.setattr(
        energy_consume_quiz.LedgerRepo, "get_by_idempotency_key", _async_return(None)
    )
    monkeypatch.setattr(energy_consume_quiz.LedgerRepo, "create", _capture_entry(created_entries))
    monkeypatch.setattr(
        energy_consume_quiz, "emit_energy_zero_event_if_needed", _async_return(None)
    )

    result = await energy_consume_quiz.consume_quiz(
        session,
        user_id=11,
        idempotency_key="energy:regen",
        now_utc=NOW_UTC,
    )

    assert result.allowed is True
    assert result.consumed_asset == "FREE_ENERGY"
    assert (state.free_energy, state.paid_energy) == (0, 0)
    assert created_entries[0].balance_after == 0


@pytest.mark.asyncio
async def test_consume_quiz_replay_does_not_debit_again_or_go_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    state = _energy_state(free_energy=0, paid_energy=0)
    existing_entry = LedgerEntry(asset="FREE_ENERGY")

    monkeypatch.setattr(
        energy_consume_quiz,
        "get_or_create_state_and_premium_status_for_update",
        _state_and_premium(state, premium_active=False),
    )
    monkeypatch.setattr(
        energy_consume_quiz.LedgerRepo,
        "get_by_idempotency_key",
        _async_return(existing_entry),
    )

    async def _unexpected_create(*_args, **_kwargs):
        pytest.fail("idempotent replay must not create another ledger row")

    monkeypatch.setattr(energy_consume_quiz.LedgerRepo, "create", _unexpected_create)

    result = await energy_consume_quiz.consume_quiz(
        session,
        user_id=11,
        idempotency_key="energy:replay",
        now_utc=NOW_UTC,
    )

    assert result.allowed is True
    assert result.idempotent_replay is True
    assert (state.free_energy, state.paid_energy) == (0, 0)


@pytest.mark.asyncio
async def test_consume_quiz_prechecked_path_skips_redundant_ledger_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    state = _energy_state(free_energy=2)
    created_entries: list[LedgerEntry] = []

    monkeypatch.setattr(
        energy_consume_quiz,
        "get_or_create_state_and_premium_status_for_update",
        _state_and_premium(state, premium_active=False),
    )

    async def _unexpected_lookup(*_args, **_kwargs):
        pytest.fail("session-prechecked start path should not repeat ledger lookup")

    monkeypatch.setattr(
        energy_consume_quiz.LedgerRepo, "get_by_idempotency_key", _unexpected_lookup
    )
    monkeypatch.setattr(energy_consume_quiz.LedgerRepo, "create", _capture_entry(created_entries))
    monkeypatch.setattr(
        energy_consume_quiz, "emit_energy_zero_event_if_needed", _async_return(None)
    )

    result = await energy_consume_quiz.consume_quiz(
        session,
        user_id=11,
        idempotency_key="energy:prechecked",
        now_utc=NOW_UTC,
        ledger_idempotency_prechecked=True,
    )

    assert result.allowed is True
    assert result.idempotent_replay is False
    assert state.free_energy == 1
    assert len(created_entries) == 1


def _capture_entry(target: list[LedgerEntry]):
    async def _inner(_session, *, entry):
        target.append(entry)
        return entry

    return _inner


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _state_and_premium(state, *, premium_active: bool):
    async def _inner(*_args, **_kwargs):
        return state, premium_active

    return _inner
