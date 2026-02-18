from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.streak_state import StreakState
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.streak_repo import StreakRepo
from app.economy.streak.rules import classify_streak_state, record_activity, rollover_to_local_date
from app.economy.streak.time import berlin_local_date
from app.economy.streak.types import StreakActivityResult, StreakSnapshot, StreakTodayStatus


class StreakService:
    @staticmethod
    def _snapshot_from_model(state: StreakState) -> StreakSnapshot:
        return StreakSnapshot(
            current_streak=state.current_streak,
            best_streak=state.best_streak,
            last_activity_local_date=state.last_activity_local_date,
            today_status=StreakTodayStatus(state.today_status),
            streak_saver_tokens=state.streak_saver_tokens,
            premium_freezes_used_week=state.premium_freezes_used_week,
            premium_freeze_week_start_local_date=state.premium_freeze_week_start_local_date,
            updated_at=state.updated_at,
        )

    @staticmethod
    def _apply_snapshot_to_model(state: StreakState, snapshot: StreakSnapshot, now_utc: datetime) -> None:
        state.current_streak = snapshot.current_streak
        state.best_streak = snapshot.best_streak
        state.last_activity_local_date = snapshot.last_activity_local_date
        state.today_status = snapshot.today_status.value
        state.streak_saver_tokens = snapshot.streak_saver_tokens
        state.premium_freezes_used_week = snapshot.premium_freezes_used_week
        state.premium_freeze_week_start_local_date = snapshot.premium_freeze_week_start_local_date
        state.updated_at = now_utc
        state.version += 1

    @staticmethod
    async def _get_or_create_state_for_update(
        session: AsyncSession,
        user_id: int,
        now_utc: datetime,
    ) -> StreakState:
        state = await StreakRepo.get_by_user_id_for_update(session, user_id)
        if state is not None:
            return state
        return await StreakRepo.create_default_state(session, user_id=user_id, now_utc=now_utc)

    @staticmethod
    async def sync_rollover(
        session: AsyncSession,
        *,
        user_id: int,
        now_utc: datetime,
    ) -> StreakSnapshot:
        state = await StreakService._get_or_create_state_for_update(session, user_id, now_utc)
        premium_scope = await EntitlementsRepo.get_active_premium_scope(session, user_id, now_utc)

        snapshot = StreakService._snapshot_from_model(state)
        snapshot = rollover_to_local_date(
            snapshot,
            target_local_date=berlin_local_date(now_utc),
            premium_scope=premium_scope,
        )

        StreakService._apply_snapshot_to_model(state, snapshot, now_utc)
        await session.flush()
        return snapshot

    @staticmethod
    async def record_activity(
        session: AsyncSession,
        *,
        user_id: int,
        activity_at_utc: datetime,
    ) -> StreakActivityResult:
        state = await StreakService._get_or_create_state_for_update(session, user_id, activity_at_utc)
        premium_scope = await EntitlementsRepo.get_active_premium_scope(session, user_id, activity_at_utc)

        local_date = berlin_local_date(activity_at_utc)
        snapshot = StreakService._snapshot_from_model(state)
        snapshot = rollover_to_local_date(
            snapshot,
            target_local_date=local_date,
            premium_scope=premium_scope,
        )
        snapshot, counted = record_activity(snapshot, local_date=local_date)

        StreakService._apply_snapshot_to_model(state, snapshot, activity_at_utc)
        await session.flush()
        return StreakActivityResult(
            counted_for_streak=counted,
            current_streak=snapshot.current_streak,
            best_streak=snapshot.best_streak,
            today_status=snapshot.today_status,
            state=classify_streak_state(snapshot),
        )
