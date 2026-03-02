from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from app.api.routes.admin.audit import write_admin_audit
from app.api.routes.admin.deps import AdminPrincipal, add_admin_noindex_header, get_current_admin
from app.api.routes.admin.pagination import build_pagination
from app.api.routes.admin.promo_models import (
    PromoBulkCreateRequest,
    PromoCreateRequest,
    PromoPatchRequest,
    generate_codes,
    normalized_code,
    serialize_promo,
    to_decimal,
)
from app.db.models.admin_promo_codes import AdminPromoCode
from app.db.repo.admin_promo_repo import AdminPromoRepo
from app.db.session import SessionLocal

router = APIRouter(prefix="/admin/promo", tags=["admin-promo"])


@router.get("")
async def list_promos(
    response: Response,
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    async with SessionLocal.begin() as session:
        items = await AdminPromoRepo.list_codes(session, status=status, page=page, limit=limit)
        total = await AdminPromoRepo.count_codes(session, status=status)
    pagination = build_pagination(total=total, page=page, limit=limit)
    return {
        "items": [serialize_promo(item) for item in items],
        "total": pagination["total"],
        "page": pagination["page"],
        "pages": pagination["pages"],
    }


@router.post("")
async def create_promo(
    payload: PromoCreateRequest,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    code = normalized_code(payload.code)
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        existing = await AdminPromoRepo.get_by_code(session, code)
        if existing is not None:
            raise HTTPException(status_code=409, detail={"code": "E_PROMO_CODE_EXISTS"})
        promo = AdminPromoCode(
            code=code,
            promo_type=payload.type,
            value=to_decimal(payload.value),
            product_code=payload.product_id,
            max_uses=payload.max_uses,
            uses_count=0,
            valid_from=payload.valid_from or now_utc,
            valid_until=payload.valid_until,
            channel_tag=payload.channel_tag,
            status="active",
            created_at=now_utc,
            updated_at=now_utc,
        )
        created = await AdminPromoRepo.create(session, promo)
        await write_admin_audit(
            session,
            admin_email=admin.email,
            action="promo_create",
            target_type="admin_promo_code",
            target_id=str(created.id),
            payload={"code": created.code, "type": created.promo_type},
            ip=admin.client_ip,
        )
    return serialize_promo(created)


@router.post("/bulk")
async def create_bulk_promos(
    payload: PromoBulkCreateRequest,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    now_utc = datetime.now(timezone.utc)
    codes = generate_codes(prefix=payload.prefix, count=payload.count)
    async with SessionLocal.begin() as session:
        collisions: list[str] = []
        for code in codes:
            if await AdminPromoRepo.get_by_code(session, code):
                collisions.append(code)
        if collisions:
            raise HTTPException(
                status_code=409, detail={"code": "E_PROMO_COLLISION", "codes": collisions[:5]}
            )
        promos = [
            AdminPromoCode(
                code=code,
                promo_type=payload.type,
                value=to_decimal(payload.value),
                product_code=payload.product_id,
                max_uses=payload.max_uses,
                uses_count=0,
                valid_from=payload.valid_from or now_utc,
                valid_until=payload.valid_until,
                channel_tag=payload.channel_tag,
                status="active",
                created_at=now_utc,
                updated_at=now_utc,
            )
            for code in codes
        ]
        created = await AdminPromoRepo.bulk_create(session, promos=promos)
        await write_admin_audit(
            session,
            admin_email=admin.email,
            action="promo_bulk_create",
            target_type="admin_promo_code",
            target_id=f"bulk:{len(created)}",
            payload={"prefix": payload.prefix, "count": len(created), "type": payload.type},
            ip=admin.client_ip,
        )
    return {"count": len(created), "items": [serialize_promo(item) for item in created]}


@router.patch("/{promo_id}")
async def patch_promo(
    promo_id: UUID,
    payload: PromoPatchRequest,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        promo = await AdminPromoRepo.get_by_id(session, promo_id)
        if promo is None:
            raise HTTPException(status_code=404, detail={"code": "E_PROMO_NOT_FOUND"})
        updated = await AdminPromoRepo.update_fields(
            session,
            promo=promo,
            now_utc=now_utc,
            value=to_decimal(payload.value) if payload.value is not None else None,
            max_uses=payload.max_uses,
            valid_until=payload.valid_until,
            channel_tag=payload.channel_tag,
            status=payload.status,
        )
        await write_admin_audit(
            session,
            admin_email=admin.email,
            action="promo_patch",
            target_type="admin_promo_code",
            target_id=str(promo_id),
            payload=payload.model_dump(exclude_none=True),
            ip=admin.client_ip,
        )
    return serialize_promo(updated)


@router.patch("/{promo_id}/toggle")
async def toggle_promo(
    promo_id: UUID,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        promo = await AdminPromoRepo.get_by_id(session, promo_id)
        if promo is None:
            raise HTTPException(status_code=404, detail={"code": "E_PROMO_NOT_FOUND"})
        next_status = "paused" if promo.status == "active" else "active"
        updated = await AdminPromoRepo.update_status(
            session, promo=promo, status=next_status, now_utc=now_utc
        )
        await write_admin_audit(
            session,
            admin_email=admin.email,
            action="promo_toggle",
            target_type="admin_promo_code",
            target_id=str(promo_id),
            payload={"status": next_status},
            ip=admin.client_ip,
        )
    return serialize_promo(updated)


@router.get("/export")
async def export_promos(
    response: Response,
    format: str = Query(default="csv"),
    _admin: AdminPrincipal = Depends(get_current_admin),
):
    add_admin_noindex_header(response)
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail={"code": "E_UNSUPPORTED_EXPORT_FORMAT"})
    async with SessionLocal.begin() as session:
        rows = await AdminPromoRepo.list_codes(session, status=None, page=1, limit=10_000)

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "code", "type", "value", "status", "uses_count", "max_uses"])
    for row in rows:
        writer.writerow(
            [
                str(row.id),
                row.code,
                row.promo_type,
                str(row.value),
                row.status,
                row.uses_count,
                row.max_uses,
            ]
        )

    headers = {"Content-Disposition": 'attachment; filename="promo_codes.csv"'}
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers=headers)


@router.get("/{promo_id}/usages")
async def list_promo_usages(
    promo_id: UUID,
    response: Response,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    async with SessionLocal.begin() as session:
        rows = await AdminPromoRepo.list_usages(session, promo_id=promo_id, page=page, limit=limit)
        total = await AdminPromoRepo.count_usages(session, promo_id=promo_id)

    pagination = build_pagination(total=total, page=page, limit=limit)
    return {
        "items": [
            {"id": int(item.id), "user_id": int(item.user_id), "used_at": item.used_at.isoformat()}
            for item in rows
        ],
        "total": pagination["total"],
        "page": pagination["page"],
        "pages": pagination["pages"],
    }
