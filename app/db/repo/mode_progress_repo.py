from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.mode_progress import ModeProgress


class ModeProgressRepo:
    @staticmethod
    async def get_by_user_mode(
        session: AsyncSession,
        *,
        user_id: int,
        mode_code: str,
    ) -> ModeProgress | None:
        return await session.get(
            ModeProgress,
            {
                "user_id": user_id,
                "mode_code": mode_code,
            },
        )

    @staticmethod
    async def get_by_user_mode_for_update(
        session: AsyncSession,
        *,
        user_id: int,
        mode_code: str,
    ) -> ModeProgress | None:
        stmt = (
            select(ModeProgress)
            .where(
                ModeProgress.user_id == user_id,
                ModeProgress.mode_code == mode_code,
            )
            .with_for_update()
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_preferred_level(
        session: AsyncSession,
        *,
        user_id: int,
        mode_code: str,
        preferred_level: str,
        now_utc: datetime,
    ) -> ModeProgress:
        state = await ModeProgressRepo.get_by_user_mode_for_update(
            session,
            user_id=user_id,
            mode_code=mode_code,
        )
        if state is None:
            state = ModeProgress(
                user_id=user_id,
                mode_code=mode_code,
                preferred_level=preferred_level,
                created_at=now_utc,
                updated_at=now_utc,
            )
            session.add(state)
            await session.flush()
            return state

        state.preferred_level = preferred_level
        state.updated_at = now_utc
        await session.flush()
        return state
