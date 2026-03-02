from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import update

from app.api.routes.admin.audit import write_admin_audit
from app.api.routes.admin.deps import AdminPrincipal, add_admin_noindex_header, get_current_admin
from app.api.routes.admin.pagination import build_pagination
from app.api.routes.admin.users_helpers import apply_bonus, get_user_profile, list_users_page
from app.db.models.energy_state import EnergyState
from app.db.models.mode_progress import ModeProgress
from app.db.models.streak_state import StreakState
from app.db.models.user_events import UserEvent
from app.db.models.users import User
from app.db.session import SessionLocal

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


class BonusRequest(BaseModel):
    type: str = Field(pattern="^(energy|streak_token|premium_days)$")
    amount: int = Field(ge=1, le=365)


class BlockRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=250)


@router.get("")
async def list_users(
    response: Response,
    search: str = Query(default=""),
    language: str | None = Query(default=None),
    level: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    async with SessionLocal.begin() as session:
        items, total = await list_users_page(
            session,
            search=search,
            language=language,
            level=level,
            page=page,
            limit=limit,
        )
    pagination = build_pagination(total=total, page=page, limit=limit)
    return {
        "items": items,
        "total": pagination["total"],
        "page": pagination["page"],
        "pages": pagination["pages"],
    }


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    response: Response,
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    async with SessionLocal.begin() as session:
        return await get_user_profile(session, user_id)


@router.post("/{user_id}/bonus")
async def grant_bonus(
    user_id: int,
    payload: BonusRequest,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    async with SessionLocal.begin() as session:
        result = await apply_bonus(
            session,
            user_id=user_id,
            bonus_type=payload.type,
            amount=payload.amount,
        )
        await write_admin_audit(
            session,
            admin_email=admin.email,
            action="user_bonus",
            target_type="user",
            target_id=str(user_id),
            payload={"type": payload.type, "amount": payload.amount},
            ip=admin.client_ip,
        )
    return {"ok": True, "result": result}


@router.post("/{user_id}/block")
async def block_user(
    user_id: int,
    payload: BlockRequest,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail={"code": "E_USER_NOT_FOUND"})
        user.status = "BLOCKED"
        session.add(
            UserEvent(user_id=user_id, event_type="admin_block", payload={"reason": payload.reason})
        )
        await write_admin_audit(
            session,
            admin_email=admin.email,
            action="user_block",
            target_type="user",
            target_id=str(user_id),
            payload={"reason": payload.reason, "at": now_utc.isoformat()},
            ip=admin.client_ip,
        )
    return {"ok": True, "user_id": user_id, "status": "BLOCKED"}


@router.post("/{user_id}/unblock")
async def unblock_user(
    user_id: int,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    async with SessionLocal.begin() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail={"code": "E_USER_NOT_FOUND"})
        user.status = "ACTIVE"
        session.add(UserEvent(user_id=user_id, event_type="admin_unblock", payload={}))
        await write_admin_audit(
            session,
            admin_email=admin.email,
            action="user_unblock",
            target_type="user",
            target_id=str(user_id),
            payload={},
            ip=admin.client_ip,
        )
    return {"ok": True, "user_id": user_id, "status": "ACTIVE"}


@router.post("/{user_id}/reset_state")
async def reset_user_state(
    user_id: int,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail={"code": "E_USER_NOT_FOUND"})

        streak = await session.get(StreakState, user_id)
        if streak is not None:
            streak.current_streak = 0
            streak.today_status = "NO_ACTIVITY"
            streak.updated_at = now_utc

        energy = await session.get(EnergyState, user_id)
        if energy is not None:
            energy.free_energy = min(energy.free_cap, 20)
            energy.paid_energy = 0
            energy.updated_at = now_utc

        await session.execute(
            update(ModeProgress)
            .where(ModeProgress.user_id == user_id)
            .values(mix_step=0, correct_in_mix=0, updated_at=now_utc)
        )
        session.add(UserEvent(user_id=user_id, event_type="admin_reset_state", payload={}))

        await write_admin_audit(
            session,
            admin_email=admin.email,
            action="user_reset_state",
            target_type="user",
            target_id=str(user_id),
            payload={"at": now_utc.isoformat()},
            ip=admin.client_ip,
        )

    return {"ok": True, "user_id": user_id}
