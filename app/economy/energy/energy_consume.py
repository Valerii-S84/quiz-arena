from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_SYSTEM, emit_analytics_event
from app.db.models.ledger_entries import LedgerEntry
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.ledger_repo import LedgerRepo
from app.economy.energy.constants import ENERGY_COST_PER_QUIZ
from app.economy.energy.energy_daily_topup import apply_daily_topup_berlin
from app.economy.energy.energy_models import (
    apply_snapshot_to_model,
    get_or_create_state_for_update,
    snapshot_from_model,
)
from app.economy.energy.energy_regen import apply_regen_tick
from app.economy.energy.rules import classify_energy_state, consume_quiz_energy
from app.economy.energy.rules import credit_paid_energy as credit_paid_energy_snapshot
from app.economy.energy.types import EnergyBucketState, EnergyConsumeResult, EnergyCreditResult


async def consume_quiz(
    session: AsyncSession,
    *,
    user_id: int,
    idempotency_key: str,
    now_utc: datetime,
) -> EnergyConsumeResult:
    state = await get_or_create_state_for_update(session, user_id, now_utc)

    existing_entry = await LedgerRepo.get_by_idempotency_key(session, idempotency_key)
    premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)
    snapshot = snapshot_from_model(state)

    if premium_active:
        if existing_entry is not None:
            return EnergyConsumeResult(
                allowed=True,
                idempotent_replay=True,
                premium_bypass=existing_entry.asset == "PREMIUM",
                consumed_asset=existing_entry.asset,
                free_energy=snapshot.free_energy,
                paid_energy=snapshot.paid_energy,
                state=classify_energy_state(snapshot, premium_active=True),
            )
        return EnergyConsumeResult(
            allowed=True,
            idempotent_replay=False,
            premium_bypass=True,
            consumed_asset="PREMIUM",
            free_energy=snapshot.free_energy,
            paid_energy=snapshot.paid_energy,
            state=classify_energy_state(snapshot, premium_active=True),
        )

    snapshot, _ = apply_regen_tick(snapshot, now_utc=now_utc, premium_active=premium_active)
    snapshot, _ = apply_daily_topup_berlin(snapshot, now_utc=now_utc)
    before_state = classify_energy_state(snapshot, premium_active=premium_active)

    if existing_entry is not None:
        apply_snapshot_to_model(state, snapshot, now_utc)
        await session.flush()
        return EnergyConsumeResult(
            allowed=True,
            idempotent_replay=True,
            premium_bypass=False,
            consumed_asset=existing_entry.asset,
            free_energy=snapshot.free_energy,
            paid_energy=snapshot.paid_energy,
            state=classify_energy_state(snapshot, premium_active=premium_active),
        )

    snapshot_after_consume, allowed, consumed_asset = consume_quiz_energy(
        snapshot,
        premium_active=premium_active,
    )

    if not allowed:
        apply_snapshot_to_model(state, snapshot_after_consume, now_utc)
        await session.flush()
        after_state = classify_energy_state(snapshot_after_consume, premium_active=premium_active)
        return EnergyConsumeResult(
            allowed=False,
            idempotent_replay=False,
            premium_bypass=False,
            consumed_asset=None,
            free_energy=snapshot_after_consume.free_energy,
            paid_energy=snapshot_after_consume.paid_energy,
            state=after_state,
        )

    if consumed_asset in {"FREE_ENERGY", "PAID_ENERGY"}:
        await LedgerRepo.create(
            session,
            entry=LedgerEntry(
                user_id=user_id,
                entry_type="ENERGY_DEBIT_QUIZ",
                asset=consumed_asset,
                direction="DEBIT",
                amount=ENERGY_COST_PER_QUIZ,
                balance_after=(
                    snapshot_after_consume.free_energy
                    if consumed_asset == "FREE_ENERGY"
                    else snapshot_after_consume.paid_energy
                ),
                source="QUIZ",
                idempotency_key=idempotency_key,
                metadata_={},
                created_at=now_utc,
            ),
        )

    apply_snapshot_to_model(state, snapshot_after_consume, now_utc)
    await session.flush()
    after_state = classify_energy_state(snapshot_after_consume, premium_active=premium_active)

    if (
        consumed_asset in {"FREE_ENERGY", "PAID_ENERGY"}
        and before_state != after_state
        and after_state == EnergyBucketState.EMPTY
    ):
        await emit_analytics_event(
            session,
            event_type="gameplay_energy_zero",
            source=EVENT_SOURCE_SYSTEM,
            user_id=user_id,
            payload={
                "consumed_asset": consumed_asset,
                "before_state": before_state.value,
                "after_state": after_state.value,
            },
            happened_at=now_utc,
        )

    return EnergyConsumeResult(
        allowed=True,
        idempotent_replay=False,
        premium_bypass=consumed_asset == "PREMIUM",
        consumed_asset=consumed_asset,
        free_energy=snapshot_after_consume.free_energy,
        paid_energy=snapshot_after_consume.paid_energy,
        state=after_state,
    )


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
