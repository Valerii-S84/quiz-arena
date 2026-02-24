from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.energy_state import EnergyState
from app.db.repo.energy_repo import EnergyRepo
from app.economy.energy.time import berlin_local_date
from app.economy.energy.types import EnergySnapshot


def snapshot_from_model(state: EnergyState) -> EnergySnapshot:
    return EnergySnapshot(
        free_energy=state.free_energy,
        paid_energy=state.paid_energy,
        free_cap=state.free_cap,
        regen_interval_sec=state.regen_interval_sec,
        last_regen_at=state.last_regen_at,
        last_daily_topup_local_date=state.last_daily_topup_local_date,
    )


def apply_snapshot_to_model(
    state: EnergyState, snapshot: EnergySnapshot, now_utc: datetime
) -> None:
    state.free_energy = snapshot.free_energy
    state.paid_energy = snapshot.paid_energy
    state.last_regen_at = snapshot.last_regen_at
    state.last_daily_topup_local_date = snapshot.last_daily_topup_local_date
    state.updated_at = now_utc
    state.version += 1


async def get_or_create_state_for_update(
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


async def initialize_user_state(
    session: AsyncSession, *, user_id: int, now_utc: datetime
) -> EnergyState:
    return await EnergyRepo.create_default_state(
        session,
        user_id=user_id,
        now_utc=now_utc,
        local_date_berlin=berlin_local_date(now_utc),
    )
