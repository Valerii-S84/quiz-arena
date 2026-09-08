from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.energy_state import EnergyState
from app.db.models.entitlements import Entitlement
from app.db.models.streak_state import StreakState
from app.db.models.user_events import UserEvent
from app.db.models.users import User
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.economy.energy.constants import (
    ENERGY_REGEN_INTERVAL_SEC,
    FREE_ENERGY_CAP,
    FREE_ENERGY_START,
)


async def _grant_premium_bonus(
    session: AsyncSession, *, user_id: int, amount: int, now_utc: datetime
) -> None:
    # Match the unique index, including ACTIVE rows whose end date has passed.
    entitlement = await EntitlementsRepo.get_premium_with_active_status_for_update(session, user_id)
    if entitlement is not None:
        if entitlement.ends_at is not None:
            entitlement.ends_at = max(entitlement.ends_at, now_utc) + timedelta(days=amount)
        entitlement.updated_at = now_utc
        return

    session.add(
        Entitlement(
            user_id=user_id,
            entitlement_type="PREMIUM",
            scope="ADMIN_BONUS",
            status="ACTIVE",
            starts_at=now_utc,
            ends_at=now_utc + timedelta(days=amount),
            source_purchase_id=None,
            idempotency_key=f"admin_bonus:{uuid4().hex}",
            metadata_={"bonus": True, "days": amount},
            created_at=now_utc,
            updated_at=now_utc,
        )
    )


async def apply_bonus(
    session: AsyncSession, *, user_id: int, bonus_type: str, amount: int
) -> dict[str, object]:
    # Serialize Premium grants even when the first entitlement does not exist yet.
    user = await session.get(User, user_id, with_for_update=bonus_type == "premium_days")
    if user is None:
        raise HTTPException(status_code=404, detail={"code": "E_USER_NOT_FOUND"})
    now_utc = datetime.now(timezone.utc)

    if bonus_type == "energy":
        energy = await session.get(EnergyState, user_id)
        if energy is None:
            energy = EnergyState(
                user_id=user_id,
                free_energy=FREE_ENERGY_START,
                paid_energy=0,
                free_cap=FREE_ENERGY_CAP,
                regen_interval_sec=ENERGY_REGEN_INTERVAL_SEC,
                last_regen_at=now_utc,
                last_daily_topup_local_date=now_utc.date(),
                version=0,
                updated_at=now_utc,
            )
            session.add(energy)
        energy.paid_energy += amount
        energy.updated_at = now_utc
    elif bonus_type == "streak_token":
        streak = await session.get(StreakState, user_id)
        if streak is None:
            streak = StreakState(
                user_id=user_id,
                current_streak=0,
                best_streak=0,
                today_status="NO_ACTIVITY",
                streak_saver_tokens=0,
                premium_freezes_used_week=0,
                version=0,
                updated_at=now_utc,
            )
            session.add(streak)
        streak.streak_saver_tokens += amount
        streak.updated_at = now_utc
    elif bonus_type == "premium_days":
        await _grant_premium_bonus(session, user_id=user_id, amount=amount, now_utc=now_utc)
    else:
        raise HTTPException(status_code=400, detail={"code": "E_INVALID_BONUS_TYPE"})

    event = UserEvent(
        user_id=user_id,
        event_type=f"admin_bonus_{bonus_type}",
        payload={"amount": amount},
    )
    session.add(event)
    await session.flush()
    return {"user_id": user_id, "bonus_type": bonus_type, "amount": amount}
