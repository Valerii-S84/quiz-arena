from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from app.api.routes.admin.deps import AdminPrincipal
from app.db.repo.promo_repo_admin_runtime import AdminRuntimePromoRepo
from app.db.session import SessionLocal

from .promo_audit import write_promo_audit
from .promo_models import PromoRevokeRequest, serialize_promo


async def toggle_promo(*, promo_id: int, admin: AdminPrincipal) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        promo = await AdminRuntimePromoRepo.get_by_id_for_update(session, promo_id)
        if promo is None:
            raise HTTPException(status_code=404, detail={"code": "E_PROMO_NOT_FOUND"})
        if promo.status not in {"ACTIVE", "PAUSED"}:
            raise HTTPException(status_code=409, detail={"code": "E_PROMO_STATUS_CONFLICT"})
        promo.status = "PAUSED" if promo.status == "ACTIVE" else "ACTIVE"
        promo.updated_at = now_utc
        await write_promo_audit(
            session,
            admin_id=admin.id,
            action="DEACTIVATE" if promo.status == "PAUSED" else "ACTIVATE",
            promo_code_id=promo.id,
            details={"status": promo.status},
        )
    return serialize_promo(promo, can_reveal_code=admin.is_super_admin)


async def revoke_promo(
    *,
    promo_id: int,
    payload: PromoRevokeRequest | None,
    admin: AdminPrincipal,
) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    revoke_reason = payload.reason.strip() if payload is not None and payload.reason else ""
    async with SessionLocal.begin() as session:
        promo = await AdminRuntimePromoRepo.get_by_id_for_update(session, promo_id)
        if promo is None:
            raise HTTPException(status_code=404, detail={"code": "E_PROMO_NOT_FOUND"})
        revoked = await AdminRuntimePromoRepo.revoke_active_reserved_redemptions(
            session,
            promo_id=promo.id,
            now_utc=now_utc,
        )
        await write_promo_audit(
            session,
            admin_id=admin.id,
            action="REVOKE",
            promo_code_id=promo.id,
            details={"revoked_count": len(revoked), "reason": revoke_reason or None},
        )
    return {
        "promo": serialize_promo(promo),
        "revoked_count": len(revoked),
        "reason": revoke_reason or None,
    }
