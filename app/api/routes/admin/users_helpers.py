from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.energy_state import EnergyState
from app.db.models.entitlements import Entitlement
from app.db.models.mode_progress import ModeProgress
from app.db.models.purchases import Purchase
from app.db.models.referrals import Referral
from app.db.models.streak_state import StreakState
from app.db.models.user_events import UserEvent
from app.db.models.users import User


def _build_search_filters(search: str) -> list[ColumnElement[bool]]:
    normalized = search.strip()
    if not normalized:
        return []

    filters: list[ColumnElement[bool]] = [
        User.username.ilike(f"%{normalized}%"),
        User.first_name.ilike(f"%{normalized}%"),
    ]
    if normalized.isdigit():
        numeric = int(normalized)
        filters.append(User.id == numeric)
        filters.append(User.telegram_user_id == numeric)
    return [or_(*filters)]


async def list_users_page(
    session: AsyncSession,
    *,
    search: str,
    language: str | None,
    level: str | None,
    page: int,
    limit: int,
) -> tuple[list[dict[str, object]], int]:
    filters: list[ColumnElement[bool]] = _build_search_filters(search)
    if language:
        filters.append(User.language_code == language)

    if level:
        level_exists = (
            select(ModeProgress.user_id)
            .where(ModeProgress.user_id == User.id, ModeProgress.preferred_level == level)
            .exists()
        )
        filters.append(level_exists)

    where_clause = and_(*filters) if filters else None
    total_stmt = select(func.count(User.id))
    if where_clause is not None:
        total_stmt = total_stmt.where(where_clause)
    total = int((await session.execute(total_stmt)).scalar_one() or 0)

    stmt = select(User)
    if where_clause is not None:
        stmt = stmt.where(where_clause)
    stmt = stmt.order_by(User.created_at.desc()).offset((page - 1) * limit).limit(limit)
    users = list((await session.execute(stmt)).scalars().all())

    user_ids = [int(user.id) for user in users]
    streak_stmt = select(StreakState.user_id, StreakState.current_streak).where(
        StreakState.user_id.in_(user_ids)
    )
    streak_map = {
        int(uid): int(streak) for uid, streak in (await session.execute(streak_stmt)).all()
    }

    rows: list[dict[str, object]] = [
        {
            "id": int(user.id),
            "telegram_user_id": int(user.telegram_user_id),
            "username": user.username,
            "first_name": user.first_name,
            "language": user.language_code,
            "status": user.status,
            "created_at": user.created_at.isoformat(),
            "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
            "streak": streak_map.get(int(user.id), 0),
        }
        for user in users
    ]
    return rows, total


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
                .where(
                    or_(Referral.referrer_user_id == user_id, Referral.referred_user_id == user_id)
                )
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
        user_id=user_id, event_type=f"admin_bonus_{bonus_type}", payload={"amount": amount}
    )
    session.add(event)
    await session.flush()
    return {"user_id": user_id, "bonus_type": bonus_type, "amount": amount}
