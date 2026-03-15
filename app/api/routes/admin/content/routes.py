from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import ModuleType
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.routes.admin.deps import AdminPrincipal, add_admin_noindex_header, get_current_admin
from app.db.models.user_events import UserEvent

from .queries import fetch_content_health_rows
from .serializers import build_content_health_payload

router = APIRouter(prefix="/admin/content", tags=["admin-content"])


def _content_module() -> ModuleType:
    return cast(ModuleType, sys.modules[__package__])


@router.get("")
async def get_content_health(
    response: Response,
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    module = _content_module()
    async with module.SessionLocal.begin() as session:
        rows = await fetch_content_health_rows(session)
    return build_content_health_payload(rows)


@router.post("/flagged/{event_id}/approve")
async def approve_flagged_question(
    event_id: int,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    module = _content_module()
    now_utc = datetime.now(timezone.utc)
    async with module.SessionLocal.begin() as session:
        event = await session.get(UserEvent, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail={"code": "E_FLAG_NOT_FOUND"})
        event.payload = {**event.payload, "review": "approved", "reviewed_at": now_utc.isoformat()}
        await module.write_admin_audit(
            session,
            admin_email=admin.email,
            action="content_flag_approve",
            target_type="user_event",
            target_id=str(event_id),
            payload={},
            ip=admin.client_ip,
        )
    return {"ok": True, "id": event_id, "review": "approved"}


@router.post("/flagged/{event_id}/reject")
async def reject_flagged_question(
    event_id: int,
    response: Response,
    reason: str = Query(default="not_reproducible"),
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    module = _content_module()
    now_utc = datetime.now(timezone.utc)
    async with module.SessionLocal.begin() as session:
        event = await session.get(UserEvent, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail={"code": "E_FLAG_NOT_FOUND"})
        event.payload = {
            **event.payload,
            "review": "rejected",
            "reason": reason,
            "reviewed_at": now_utc.isoformat(),
        }
        await module.write_admin_audit(
            session,
            admin_email=admin.email,
            action="content_flag_reject",
            target_type="user_event",
            target_id=str(event_id),
            payload={"reason": reason},
            ip=admin.client_ip,
        )
    return {"ok": True, "id": event_id, "review": "rejected", "reason": reason}
