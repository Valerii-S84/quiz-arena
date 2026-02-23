from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.energy_repo import EnergyRepo
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.streak_repo import StreakRepo
from app.economy.energy.constants import FREE_ENERGY_START
from app.economy.offers.constants import (
    COMEBACK_WINDOW_DAYS,
    ENERGY10_SECOND_BUY_WINDOW,
    MEGA_THIRD_BUY_WINDOW,
    MONTH_EXPIRING_WINDOW,
    STARTER_EXPIRED_WINDOW,
    TRG_COMEBACK_3D,
    TRG_ENERGY10_SECOND_BUY,
    TRG_ENERGY_LOW,
    TRG_ENERGY_ZERO,
    TRG_LOCKED_MODE_CLICK,
    TRG_MEGA_THIRD_BUY,
    TRG_MONTH_EXPIRING,
    TRG_STARTER_EXPIRED,
    TRG_STREAK_GT7,
    TRG_STREAK_MILESTONE_30,
    TRG_STREAK_RISK_22,
    TRG_WEEKEND_FLASH,
)
from app.economy.offers.time_utils import berlin_now, is_weekend_flash_window


async def build_trigger_codes(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
    trigger_event: str | None,
) -> set[str]:
    trigger_codes: set[str] = set()
    berlin_now_dt = berlin_now(now_utc)
    berlin_today = berlin_now_dt.date()

    energy_state = await EnergyRepo.get_by_user_id(session, user_id)
    total_energy = (
        FREE_ENERGY_START
        if energy_state is None
        else max(0, int(energy_state.free_energy) + int(energy_state.paid_energy))
    )

    streak_state = await StreakRepo.get_by_user_id(session, user_id)
    current_streak = 0 if streak_state is None else int(streak_state.current_streak)
    today_status = "NO_ACTIVITY" if streak_state is None else streak_state.today_status
    last_activity_local_date: date | None = (
        None if streak_state is None else streak_state.last_activity_local_date
    )

    premium_active = await EntitlementsRepo.has_active_premium(session, user_id, now_utc)

    if not premium_active and total_energy == 0:
        trigger_codes.add(TRG_ENERGY_ZERO)
    if not premium_active and 1 <= total_energy <= 3:
        trigger_codes.add(TRG_ENERGY_LOW)

    energy10_count = await PurchasesRepo.count_paid_product_since(
        session,
        user_id=user_id,
        product_code="ENERGY_10",
        since_utc=now_utc - ENERGY10_SECOND_BUY_WINDOW,
    )
    if not premium_active and energy10_count >= 2:
        trigger_codes.add(TRG_ENERGY10_SECOND_BUY)

    if trigger_event == TRG_LOCKED_MODE_CLICK and not premium_active:
        trigger_codes.add(TRG_LOCKED_MODE_CLICK)

    if current_streak > 7:
        trigger_codes.add(TRG_STREAK_GT7)
    if current_streak > 14 and berlin_now_dt.hour >= 22 and today_status == "NO_ACTIVITY":
        trigger_codes.add(TRG_STREAK_RISK_22)
    if current_streak >= 30:
        trigger_codes.add(TRG_STREAK_MILESTONE_30)

    if last_activity_local_date is not None:
        if (berlin_today - last_activity_local_date).days >= COMEBACK_WINDOW_DAYS:
            trigger_codes.add(TRG_COMEBACK_3D)

    mega_count = await PurchasesRepo.count_paid_product_since(
        session,
        user_id=user_id,
        product_code="MEGA_PACK_15",
        since_utc=now_utc - MEGA_THIRD_BUY_WINDOW,
    )
    if not premium_active and mega_count >= 3:
        trigger_codes.add(TRG_MEGA_THIRD_BUY)

    starter_expired_recently = await EntitlementsRepo.has_recently_ended_premium_scope(
        session,
        user_id=user_id,
        scope="PREMIUM_STARTER",
        since_utc=now_utc - STARTER_EXPIRED_WINDOW,
        until_utc=now_utc,
    )
    if not premium_active and starter_expired_recently:
        trigger_codes.add(TRG_STARTER_EXPIRED)

    month_expiring = await EntitlementsRepo.has_active_premium_scope_ending_within(
        session,
        user_id=user_id,
        scope="PREMIUM_MONTH",
        now_utc=now_utc,
        until_utc=now_utc + MONTH_EXPIRING_WINDOW,
    )
    if month_expiring:
        trigger_codes.add(TRG_MONTH_EXPIRING)

    if is_weekend_flash_window(berlin_now_dt):
        trigger_codes.add(TRG_WEEKEND_FLASH)

    return trigger_codes
