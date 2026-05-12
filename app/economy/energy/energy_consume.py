from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ledger_entries import LedgerEntry
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.ledger_repo import LedgerRepo
from app.economy.energy.energy_consume_quiz import consume_quiz as consume_quiz
from app.economy.energy.energy_daily_topup import apply_daily_topup_berlin
from app.economy.energy.energy_models import (
    apply_snapshot_to_model,
    get_or_create_state_for_update,
    snapshot_from_model,
)
from app.economy.energy.energy_regen import apply_regen_tick
from app.economy.energy.rules import classify_energy_state
from app.economy.energy.rules import credit_free_energy as credit_free_energy_snapshot
from app.economy.energy.rules import credit_paid_energy as credit_paid_energy_snapshot
from app.economy.energy.types import EnergyCreditResult


async def credit_paid_energy(
    session: AsyncSession,
    *,
    user_id: int,
    amount: int,
    idempotency_key: str,
    now_utc: datetime,
    source: str = "PURCHASE",
    write_ledger_entry: bool = True,
) -> EnergyCreditResult:
    if amount <= 0:
        raise ValueError("amount must be positive")

    state = await get_or_create_state_for_update(session, user_id, now_utc)
    existing_entry = None
    if write_ledger_entry:
        existing_entry = await LedgerRepo.get_by_idempotency_key(session, idempotency_key)
    premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)

    snapshot = snapshot_from_model(state)
    snapshot, _ = apply_regen_tick(snapshot, now_utc=now_utc, premium_active=premium_active)
    snapshot, _ = apply_daily_topup_berlin(snapshot, now_utc=now_utc)

    if existing_entry is None:
        snapshot = credit_paid_energy_snapshot(snapshot, amount=amount)
        if write_ledger_entry:
            await LedgerRepo.create(
                session,
                entry=LedgerEntry(
                    user_id=user_id,
                    entry_type="PURCHASE_CREDIT",
                    asset="PAID_ENERGY",
                    direction="CREDIT",
                    amount=amount,
                    balance_after=snapshot.paid_energy,
                    source=source,
                    idempotency_key=idempotency_key,
                    metadata_={},
                    created_at=now_utc,
                ),
            )

    apply_snapshot_to_model(state, snapshot, now_utc)
    await session.flush()
    return EnergyCreditResult(
        amount=amount,
        idempotent_replay=existing_entry is not None if write_ledger_entry else False,
        free_energy=snapshot.free_energy,
        paid_energy=snapshot.paid_energy,
        state=classify_energy_state(snapshot, premium_active=premium_active),
    )


async def credit_free_energy(
    session: AsyncSession,
    *,
    user_id: int,
    amount: int,
    idempotency_key: str,
    now_utc: datetime,
    source: str = "SYSTEM",
    write_ledger_entry: bool = True,
) -> EnergyCreditResult:
    if amount <= 0:
        raise ValueError("amount must be positive")

    state = await get_or_create_state_for_update(session, user_id, now_utc)
    existing_entry = None
    if write_ledger_entry:
        existing_entry = await LedgerRepo.get_by_idempotency_key(session, idempotency_key)
    premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)

    snapshot = snapshot_from_model(state)
    snapshot, _ = apply_regen_tick(snapshot, now_utc=now_utc, premium_active=premium_active)
    snapshot, _ = apply_daily_topup_berlin(snapshot, now_utc=now_utc)
    credited_amount = 0

    if existing_entry is None:
        free_energy_before = snapshot.free_energy
        snapshot = credit_free_energy_snapshot(snapshot, amount=amount)
        credited_amount = snapshot.free_energy - free_energy_before
        if write_ledger_entry and credited_amount > 0:
            await LedgerRepo.create(
                session,
                entry=LedgerEntry(
                    user_id=user_id,
                    entry_type="FREE_ENERGY_CREDIT",
                    asset="FREE_ENERGY",
                    direction="CREDIT",
                    amount=credited_amount,
                    balance_after=snapshot.free_energy,
                    source=source,
                    idempotency_key=idempotency_key,
                    metadata_={},
                    created_at=now_utc,
                ),
            )
    else:
        credited_amount = int(existing_entry.amount)

    apply_snapshot_to_model(state, snapshot, now_utc)
    await session.flush()
    return EnergyCreditResult(
        amount=credited_amount,
        idempotent_replay=existing_entry is not None if write_ledger_entry else False,
        free_energy=snapshot.free_energy,
        paid_energy=snapshot.paid_energy,
        state=classify_energy_state(snapshot, premium_active=premium_active),
    )
