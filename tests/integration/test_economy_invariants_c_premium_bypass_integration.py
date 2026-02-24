from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models.energy_state import EnergyState
from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.repo.energy_repo import EnergyRepo
from app.db.session import SessionLocal
from app.economy.energy.service import EnergyService
from app.economy.energy.time import berlin_local_date
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_premium_bypass_does_not_change_free_or_paid_energy() -> None:
    now_utc = datetime(2026, 2, 18, 15, 0, tzinfo=UTC)
    user_id = await _create_user("inv-c-premium-bypass")

    async with SessionLocal.begin() as session:
        session.add(
            EnergyState(
                user_id=user_id,
                free_energy=4,
                paid_energy=9,
                free_cap=20,
                regen_interval_sec=1800,
                last_regen_at=now_utc,
                last_daily_topup_local_date=berlin_local_date(now_utc),
                version=0,
                updated_at=now_utc,
            )
        )
        session.add(
            Entitlement(
                user_id=user_id,
                entitlement_type="PREMIUM",
                scope="PREMIUM_MONTH",
                status="ACTIVE",
                starts_at=now_utc,
                ends_at=now_utc + timedelta(days=1),
                source_purchase_id=None,
                idempotency_key="inv-c-premium-bypass:entitlement",
                metadata_={},
                created_at=now_utc,
                updated_at=now_utc,
            )
        )

    async with SessionLocal.begin() as session:
        result = await EnergyService.consume_quiz(
            session,
            user_id=user_id,
            idempotency_key="inv-c-premium-bypass:consume",
            now_utc=now_utc,
        )
    assert result.allowed is True
    assert result.premium_bypass is True
    assert result.consumed_asset == "PREMIUM"

    async with SessionLocal.begin() as session:
        state = await EnergyRepo.get_by_user_id(session, user_id)
        assert state is not None
        assert state.free_energy == 4
        assert state.paid_energy == 9

        entry = await session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.idempotency_key == "inv-c-premium-bypass:consume",
            )
        )
        assert entry is None


@pytest.mark.asyncio
async def test_non_premium_consume_decrements_paid_bucket_when_free_empty() -> None:
    now_utc = datetime(2026, 2, 18, 15, 10, tzinfo=UTC)
    user_id = await _create_user("inv-c-non-premium-paid-bucket")

    async with SessionLocal.begin() as session:
        session.add(
            EnergyState(
                user_id=user_id,
                free_energy=0,
                paid_energy=3,
                free_cap=20,
                regen_interval_sec=1800,
                last_regen_at=now_utc,
                last_daily_topup_local_date=berlin_local_date(now_utc),
                version=0,
                updated_at=now_utc,
            )
        )

    async with SessionLocal.begin() as session:
        result = await EnergyService.consume_quiz(
            session,
            user_id=user_id,
            idempotency_key="inv-c-non-premium-paid-bucket:consume",
            now_utc=now_utc,
        )

    assert result.allowed is True
    assert result.premium_bypass is False
    assert result.consumed_asset == "PAID_ENERGY"
    assert result.free_energy == 0
    assert result.paid_energy == 2

    async with SessionLocal.begin() as session:
        state = await EnergyRepo.get_by_user_id(session, user_id)
        assert state is not None
        assert state.free_energy == 0
        assert state.paid_energy == 2

        debit_entry = await session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.idempotency_key == "inv-c-non-premium-paid-bucket:consume",
            )
        )
        assert debit_entry is not None
        assert debit_entry.asset == "PAID_ENERGY"
        assert debit_entry.direction == "DEBIT"
