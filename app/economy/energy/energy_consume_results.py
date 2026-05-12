from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_SYSTEM, emit_analytics_event
from app.db.models.ledger_entries import LedgerEntry
from app.economy.energy.constants import ENERGY_COST_PER_QUIZ
from app.economy.energy.rules import classify_energy_state
from app.economy.energy.types import EnergyBucketState, EnergyConsumeResult, EnergySnapshot

CONSUMABLE_ENERGY_ASSETS = frozenset({"FREE_ENERGY", "PAID_ENERGY"})


def build_consume_result(
    *,
    snapshot: EnergySnapshot,
    premium_active: bool,
    allowed: bool,
    idempotent_replay: bool,
    consumed_asset: str | None,
) -> EnergyConsumeResult:
    return EnergyConsumeResult(
        allowed=allowed,
        idempotent_replay=idempotent_replay,
        premium_bypass=consumed_asset == "PREMIUM",
        consumed_asset=consumed_asset,
        free_energy=snapshot.free_energy,
        paid_energy=snapshot.paid_energy,
        state=classify_energy_state(snapshot, premium_active=premium_active),
    )


def build_quiz_debit_entry(
    *,
    user_id: int,
    consumed_asset: str | None,
    snapshot: EnergySnapshot,
    idempotency_key: str,
    now_utc: datetime,
) -> LedgerEntry | None:
    if consumed_asset not in CONSUMABLE_ENERGY_ASSETS:
        return None

    return LedgerEntry(
        user_id=user_id,
        entry_type="ENERGY_DEBIT_QUIZ",
        asset=consumed_asset,
        direction="DEBIT",
        amount=ENERGY_COST_PER_QUIZ,
        balance_after=(
            snapshot.free_energy if consumed_asset == "FREE_ENERGY" else snapshot.paid_energy
        ),
        source="QUIZ",
        idempotency_key=idempotency_key,
        metadata_={},
        created_at=now_utc,
    )


async def emit_energy_zero_event_if_needed(
    session: AsyncSession,
    *,
    user_id: int,
    consumed_asset: str | None,
    before_state: EnergyBucketState,
    after_state: EnergyBucketState,
    now_utc: datetime,
) -> None:
    if consumed_asset not in CONSUMABLE_ENERGY_ASSETS:
        return
    if before_state == after_state or after_state != EnergyBucketState.EMPTY:
        return

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
