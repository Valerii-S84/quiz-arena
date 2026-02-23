from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.energy_state import EnergyState
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.economy.energy.constants import ENERGY_COST_PER_QUIZ, FREE_ENERGY_CAP, FREE_ENERGY_START
from app.economy.energy.energy_consume import credit_paid_energy, consume_quiz
from app.economy.energy.energy_daily_topup import apply_daily_topup_berlin
from app.economy.energy.energy_models import (
    apply_snapshot_to_model,
    get_or_create_state_for_update,
    initialize_user_state,
    snapshot_from_model,
)
from app.economy.energy.energy_regen import apply_regen_tick
from app.economy.energy.types import EnergyConsumeResult, EnergyCreditResult, EnergySnapshot


class EnergyService:
    @staticmethod
    def _snapshot_from_model(state: EnergyState) -> EnergySnapshot:
        return snapshot_from_model(state)

    @staticmethod
    def _apply_snapshot_to_model(
        state: EnergyState, snapshot: EnergySnapshot, now_utc: datetime
    ) -> None:
        apply_snapshot_to_model(state, snapshot, now_utc)

    @staticmethod
    async def _get_or_create_state_for_update(
        session: AsyncSession,
        user_id: int,
        now_utc: datetime,
    ) -> EnergyState:
        return await get_or_create_state_for_update(session, user_id, now_utc)

    @staticmethod
    async def consume_quiz(
        session: AsyncSession,
        *,
        user_id: int,
        idempotency_key: str,
        now_utc: datetime,
    ) -> EnergyConsumeResult:
        return await consume_quiz(
            session,
            user_id=user_id,
            idempotency_key=idempotency_key,
            now_utc=now_utc,
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
        return await credit_paid_energy(
            session,
            user_id=user_id,
            amount=amount,
            idempotency_key=idempotency_key,
            now_utc=now_utc,
            source=source,
        )

    @staticmethod
    async def sync_energy_clock(
        session: AsyncSession, *, user_id: int, now_utc: datetime
    ) -> EnergySnapshot:
        state = await EnergyService._get_or_create_state_for_update(session, user_id, now_utc)
        premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)

        snapshot = EnergyService._snapshot_from_model(state)
        snapshot, _ = apply_regen_tick(snapshot, now_utc=now_utc, premium_active=premium_active)
        snapshot, _ = apply_daily_topup_berlin(snapshot, now_utc=now_utc)

        EnergyService._apply_snapshot_to_model(state, snapshot, now_utc)
        await session.flush()
        return snapshot

    @staticmethod
    async def initialize_user_state(
        session: AsyncSession, *, user_id: int, now_utc: datetime
    ) -> EnergyState:
        return await initialize_user_state(session, user_id=user_id, now_utc=now_utc)

    @staticmethod
    def default_values() -> dict[str, int]:
        return {
            "free_energy_start": FREE_ENERGY_START,
            "free_energy_cap": FREE_ENERGY_CAP,
            "energy_cost_per_quiz": ENERGY_COST_PER_QUIZ,
        }
