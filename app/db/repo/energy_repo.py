from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.energy_state import EnergyState


class EnergyRepo:
    @staticmethod
    async def get_by_user_id(session: AsyncSession, user_id: int) -> EnergyState | None:
        return await session.get(EnergyState, user_id)

    @staticmethod
    async def get_by_user_id_for_update(session: AsyncSession, user_id: int) -> EnergyState | None:
        stmt = select(EnergyState).where(EnergyState.user_id == user_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_default_state(
        session: AsyncSession,
        *,
        user_id: int,
        now_utc: datetime,
        local_date_berlin: date,
    ) -> EnergyState:
        state = EnergyState(
            user_id=user_id,
            free_energy=20,
            paid_energy=0,
            free_cap=20,
            regen_interval_sec=1800,
            last_regen_at=now_utc,
            last_daily_topup_local_date=local_date_berlin,
            version=0,
            updated_at=now_utc,
        )
        session.add(state)
        await session.flush()
        return state
