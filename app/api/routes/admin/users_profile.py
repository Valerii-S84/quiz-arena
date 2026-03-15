from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.energy_state import EnergyState
from app.db.models.mode_progress import ModeProgress
from app.db.models.purchases import Purchase
from app.db.models.referrals import Referral
from app.db.models.streak_state import StreakState
from app.db.models.user_events import UserEvent
from app.db.models.users import User


async def get_user_profile(session: AsyncSession, user_id: int) -> dict[str, object]:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"code": "E_USER_NOT_FOUND"})

    streak = await session.get(StreakState, user_id)
    energy = await session.get(EnergyState, user_id)
    levels = (
        await session.execute(
            select(ModeProgress.mode_code, ModeProgress.preferred_level).where(
                ModeProgress.user_id == user_id
            )
        )
    ).all()

    purchases = (
        (
            await session.execute(
                select(Purchase)
                .where(Purchase.user_id == user_id)
                .order_by(Purchase.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    referrals = (
        (
            await session.execute(
                select(Referral)
                .where(or_(Referral.referrer_user_id == user_id, Referral.referred_user_id == user_id))
                .order_by(Referral.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    analytics_events = (
        await session.execute(
            select(AnalyticsEvent.event_type, AnalyticsEvent.created_at, AnalyticsEvent.payload)
            .where(AnalyticsEvent.user_id == user_id)
            .order_by(AnalyticsEvent.created_at.desc())
            .limit(50)
        )
    ).all()
    admin_events = (
        await session.execute(
            select(UserEvent.event_type, UserEvent.created_at, UserEvent.payload)
            .where(UserEvent.user_id == user_id)
            .order_by(UserEvent.created_at.desc())
            .limit(50)
        )
    ).all()

    timeline_rows = list(analytics_events) + list(admin_events)
    timeline = [
        {"type": event_type, "created_at": created_at.isoformat(), "payload": payload}
        for event_type, created_at, payload in timeline_rows
    ]
    timeline.sort(key=lambda item: str(item["created_at"]), reverse=True)

    return {
        "info": {
            "id": int(user.id),
            "telegram_user_id": int(user.telegram_user_id),
            "username": user.username,
            "first_name": user.first_name,
            "language": user.language_code,
            "status": user.status,
            "created_at": user.created_at.isoformat(),
            "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
        },
        "progress": {
            "levels": [{"mode": mode, "level": level} for mode, level in levels],
            "streak": int(streak.current_streak) if streak else 0,
            "best_streak": int(streak.best_streak) if streak else 0,
            "paid_energy": int(energy.paid_energy) if energy else 0,
        },
        "purchases": [
            {
                "id": str(purchase.id),
                "product": purchase.product_code,
                "stars": int(purchase.stars_amount),
                "status": purchase.status,
                "paid_at": purchase.paid_at.isoformat() if purchase.paid_at else None,
            }
            for purchase in purchases
        ],
        "referrals": [
            {
                "id": int(ref.id),
                "referrer_user_id": int(ref.referrer_user_id),
                "referred_user_id": int(ref.referred_user_id),
                "status": ref.status,
                "created_at": ref.created_at.isoformat(),
            }
            for ref in referrals
        ],
        "timeline": timeline[:80],
    }
