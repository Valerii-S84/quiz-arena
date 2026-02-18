from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.streak_state import StreakState


class StreakRepo:
    @staticmethod
    async def get_by_user_id(session: AsyncSession, user_id: int) -> StreakState | None:
        return await session.get(StreakState, user_id)

    @staticmethod
    async def get_by_user_id_for_update(session: AsyncSession, user_id: int) -> StreakState | None:
        stmt = select(StreakState).where(StreakState.user_id == user_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_default_state(session: AsyncSession, *, user_id: int, now_utc: datetime) -> StreakState:
        state = StreakState(
            user_id=user_id,
            current_streak=0,
            best_streak=0,
            today_status="NO_ACTIVITY",
            streak_saver_tokens=0,
            premium_freezes_used_week=0,
            version=0,
            updated_at=now_utc,
        )
        session.add(state)
        await session.flush()
        return state
