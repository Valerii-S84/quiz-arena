from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_SYSTEM, emit_analytics_event
from app.db.models.energy_state import EnergyState
from app.db.models.ledger_entries import LedgerEntry
from app.db.repo.energy_repo import EnergyRepo
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.ledger_repo import LedgerRepo
from app.economy.energy.constants import ENERGY_COST_PER_QUIZ, FREE_ENERGY_CAP, FREE_ENERGY_START
from app.economy.energy.rules import (
    apply_daily_topup,
    apply_regen,
    classify_energy_state,
    consume_quiz_energy,
    credit_paid_energy,
)
from app.economy.energy.time import berlin_local_date
from app.economy.energy.types import EnergyBucketState, EnergyConsumeResult, EnergyCreditResult, EnergySnapshot


class EnergyService:
    @staticmethod
    def _snapshot_from_model(state: EnergyState) -> EnergySnapshot:
        return EnergySnapshot(
            free_energy=state.free_energy,
            paid_energy=state.paid_energy,
            free_cap=state.free_cap,
            regen_interval_sec=state.regen_interval_sec,
            last_regen_at=state.last_regen_at,
            last_daily_topup_local_date=state.last_daily_topup_local_date,
        )

    @staticmethod
    def _apply_snapshot_to_model(state: EnergyState, snapshot: EnergySnapshot, now_utc: datetime) -> None:
        state.free_energy = snapshot.free_energy
        state.paid_energy = snapshot.paid_energy
        state.last_regen_at = snapshot.last_regen_at
        state.last_daily_topup_local_date = snapshot.last_daily_topup_local_date
        state.updated_at = now_utc
        state.version += 1

    @staticmethod
    async def _get_or_create_state_for_update(
        session: AsyncSession,
        user_id: int,
        now_utc: datetime,
    ) -> EnergyState:
        state = await EnergyRepo.get_by_user_id_for_update(session, user_id)
        if state is not None:
            return state

        return await EnergyRepo.create_default_state(
            session,
            user_id=user_id,
            now_utc=now_utc,
            local_date_berlin=berlin_local_date(now_utc),
        )

    @staticmethod
    async def consume_quiz(
        session: AsyncSession,
        *,
        user_id: int,
        idempotency_key: str,
        now_utc: datetime,
    ) -> EnergyConsumeResult:
        state = await EnergyService._get_or_create_state_for_update(session, user_id, now_utc)

        existing_entry = await LedgerRepo.get_by_idempotency_key(session, idempotency_key)
        premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)
        snapshot = EnergyService._snapshot_from_model(state)

        snapshot, _ = apply_regen(snapshot, now_utc=now_utc, premium_active=premium_active)
        snapshot, _ = apply_daily_topup(snapshot, local_date_berlin=berlin_local_date(now_utc))
        before_state = classify_energy_state(snapshot, premium_active=premium_active)

        if existing_entry is not None:
            EnergyService._apply_snapshot_to_model(state, snapshot, now_utc)
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
            EnergyService._apply_snapshot_to_model(state, snapshot_after_consume, now_utc)
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

        EnergyService._apply_snapshot_to_model(state, snapshot_after_consume, now_utc)
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

    @staticmethod
    async def credit_paid_energy(
        session: AsyncSession,
        *,
        user_id: int,
        amount: int,
        idempotency_key: str,
        now_utc: datetime,
        source: str = "PURCHASE",
    ) -> EnergyCreditResult:
        if amount <= 0:
            raise ValueError("amount must be positive")

        state = await EnergyService._get_or_create_state_for_update(session, user_id, now_utc)
        existing_entry = await LedgerRepo.get_by_idempotency_key(session, idempotency_key)
        premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)

        snapshot = EnergyService._snapshot_from_model(state)
        snapshot, _ = apply_regen(snapshot, now_utc=now_utc, premium_active=premium_active)
        snapshot, _ = apply_daily_topup(snapshot, local_date_berlin=berlin_local_date(now_utc))

        if existing_entry is None:
            snapshot = credit_paid_energy(snapshot, amount=amount)
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

        EnergyService._apply_snapshot_to_model(state, snapshot, now_utc)
        await session.flush()
        return EnergyCreditResult(
            amount=amount,
            idempotent_replay=existing_entry is not None,
            free_energy=snapshot.free_energy,
            paid_energy=snapshot.paid_energy,
            state=classify_energy_state(snapshot, premium_active=premium_active),
        )

    @staticmethod
    async def sync_energy_clock(session: AsyncSession, *, user_id: int, now_utc: datetime) -> EnergySnapshot:
        state = await EnergyService._get_or_create_state_for_update(session, user_id, now_utc)
        premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)

        snapshot = EnergyService._snapshot_from_model(state)
        snapshot, _ = apply_regen(snapshot, now_utc=now_utc, premium_active=premium_active)
        snapshot, _ = apply_daily_topup(snapshot, local_date_berlin=berlin_local_date(now_utc))

        EnergyService._apply_snapshot_to_model(state, snapshot, now_utc)
        await session.flush()
        return snapshot

    @staticmethod
    async def initialize_user_state(session: AsyncSession, *, user_id: int, now_utc: datetime) -> EnergyState:
        return await EnergyRepo.create_default_state(
            session,
            user_id=user_id,
            now_utc=now_utc,
            local_date_berlin=berlin_local_date(now_utc),
        )

    @staticmethod
    def default_values() -> dict[str, int]:
        return {
            "free_energy_start": FREE_ENERGY_START,
            "free_energy_cap": FREE_ENERGY_CAP,
            "energy_cost_per_quiz": ENERGY_COST_PER_QUIZ,
        }
