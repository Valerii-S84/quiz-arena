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


async def apply_bonus(
    session: AsyncSession, *, user_id: int, bonus_type: str, amount: int
) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"code": "E_USER_NOT_FOUND"})

    if bonus_type == "energy":
        energy = await session.get(EnergyState, user_id)
        if energy is None:
            energy = EnergyState(
                user_id=user_id,
                free_energy=20,
                paid_energy=0,
                free_cap=20,
                regen_interval_sec=1800,
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
        entitlement = Entitlement(
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
        session.add(entitlement)
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
