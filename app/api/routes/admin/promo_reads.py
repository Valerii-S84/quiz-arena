from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.api.routes.admin.audit import write_admin_audit
from app.api.routes.admin.deps import AdminPrincipal
from app.api.routes.admin.pagination import build_pagination
from app.core.config import get_settings
from app.db.repo.promo_audit_repo import PromoAuditRepo
from app.db.repo.promo_repo_admin_runtime import AdminRuntimePromoRepo
from app.db.session import SessionLocal
from app.economy.purchases.catalog import PRODUCTS, get_product, is_product_available_for_sale
from app.services.promo_codes import hash_promo_code, normalize_promo_code
from app.services.promo_encryption import decrypt_promo_code

from .promo_audit import write_promo_audit
from .promo_models import OPEN_ENDED_VALID_UNTIL, raw_code_value, serialize_promo


def _serialize_redemption(
    *, user_id: int, redeemed_at: datetime, status: str, product_id: str | None
) -> dict[str, object]:
    return {
        "user_id": user_id,
        "redeemed_at": redeemed_at.isoformat(),
        "status": status,
        "product_id": product_id,
    }


def _code_hash(raw_code: str) -> str:
    return hash_promo_code(
        normalized_code=normalize_promo_code(raw_code),
        pepper=get_settings().promo_secret_pepper,
    )


async def list_promos(
    *, status: str | None, query: str | None, page: int, limit: int
) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    if status is not None and status not in {"active", "inactive", "expired"}:
        raise HTTPException(status_code=422, detail={"code": "E_PROMO_STATUS_INVALID"})

    async with SessionLocal.begin() as session:
        items = await AdminRuntimePromoRepo.list_codes(
            session,
            status=status,
            query=query,
            page=page,
            limit=limit,
            now_utc=now_utc,
        )
        total = await AdminRuntimePromoRepo.count_codes(
            session,
            status=status,
            query=query,
            now_utc=now_utc,
        )

    pagination = build_pagination(total=total, page=page, limit=limit)
    return {
        "items": [serialize_promo(item, now_utc=now_utc) for item in items],
        "total": pagination["total"],
        "page": pagination["page"],
        "pages": pagination["pages"],
    }


async def get_promo(*, promo_id: int, admin: AdminPrincipal, reveal: bool) -> dict[str, object]:
    async with SessionLocal.begin() as session:
        promo = await AdminRuntimePromoRepo.get_by_id(session, promo_id)
        if promo is None:
            raise HTTPException(status_code=404, detail={"code": "E_PROMO_NOT_FOUND"})

        raw_code: str | None = None
        if reveal and admin.is_super_admin and promo.code_encrypted is not None:
            try:
                raw_code = decrypt_promo_code(promo.code_encrypted)
            except ValueError as exc:
                raise HTTPException(
                    status_code=500, detail={"code": "E_PROMO_DECRYPT_FAILED"}
                ) from exc
            await write_admin_audit(
                session,
                admin_email=admin.email,
                action="promo_reveal_code",
                target_type="promo_code",
                target_id=str(promo_id),
                payload={"code_prefix": promo.code_prefix},
                ip=admin.client_ip,
            )
            await write_promo_audit(
                session,
                admin_id=admin.id,
                action="REVEAL_CODE",
                promo_code_id=promo.id,
                details={"code_prefix": promo.code_prefix},
            )
    return serialize_promo(
        promo,
        raw_code=raw_code,
        can_reveal_code=admin.is_super_admin,
    )


async def get_promo_stats(*, promo_id: int) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        promo = await AdminRuntimePromoRepo.get_by_id(session, promo_id)
        if promo is None:
            raise HTTPException(status_code=404, detail={"code": "E_PROMO_NOT_FOUND"})
        reserved_active = await AdminRuntimePromoRepo.count_active_reserved_redemptions(
            session,
            promo_id=promo_id,
            now_utc=now_utc,
        )
        status_totals = await AdminRuntimePromoRepo.count_redemptions_by_status(
            session,
            promo_id=promo_id,
        )
        redemptions = await AdminRuntimePromoRepo.list_recent_redemptions(
            session, promo_id=promo_id
        )
    return {
        "used_total": promo.used_total,
        "reserved_active": reserved_active,
        "status_totals": status_totals,
        "redemptions": [
            _serialize_redemption(
                user_id=int(redemption.user_id),
                redeemed_at=redemption.applied_at or redemption.updated_at or redemption.created_at,
                status=redemption.status,
                product_id=product_id,
            )
            for redemption, product_id in redemptions
        ],
    }


async def list_promo_audit(*, promo_id: int, limit: int = 100) -> dict[str, object]:
    async with SessionLocal.begin() as session:
        promo = await AdminRuntimePromoRepo.get_by_id(session, promo_id)
        if promo is None:
            raise HTTPException(status_code=404, detail={"code": "E_PROMO_NOT_FOUND"})
        items = await PromoAuditRepo.list_for_promo(session, promo_code_id=promo_id, limit=limit)
    return {
        "items": [
            {
                "id": str(item.id),
                "action": item.action,
                "admin": admin_email,
                "details": item.details,
                "created_at": item.created_at.isoformat(),
            }
            for item, admin_email in items
        ]
    }


async def check_promo_code(*, code: str) -> dict[str, object]:
    normalized = raw_code_value(code)
    if not normalized:
        return {"normalized_code": "", "exists": False}

    async with SessionLocal.begin() as session:
        promo = await AdminRuntimePromoRepo.get_by_hash(session, _code_hash(normalized))
    return {"normalized_code": normalized, "exists": promo is not None}


async def list_promo_products() -> dict[str, object]:
    items = []
    for product_code, spec in PRODUCTS.items():
        if not is_product_available_for_sale(product_code):
            continue
        product = get_product(product_code)
        if product is None:
            continue
        items.append(
            {
                "id": product.product_code,
                "title": product.title,
                "product_type": product.product_type,
                "stars_amount": product.stars_amount,
            }
        )
    items.sort(key=lambda item: (str(item["product_type"]), str(item["title"])))
    return {"items": items}


async def export_promos() -> StreamingResponse:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        rows = await AdminRuntimePromoRepo.list_codes(
            session,
            status=None,
            query=None,
            page=1,
            limit=10_000,
            now_utc=now_utc,
        )

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["code", "campaign_name", "discount_type", "discount_value", "valid_until"])
    for row in rows:
        serialized = serialize_promo(row, now_utc=now_utc)
        writer.writerow(
            [
                serialized["code"],
                serialized["campaign_name"],
                serialized["discount_type"],
                serialized["discount_value"] or "",
                "" if row.valid_until >= OPEN_ENDED_VALID_UNTIL else serialized["valid_until"],
            ]
        )

    headers = {"Content-Disposition": 'attachment; filename="promo_codes.csv"'}
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers=headers)


async def list_promo_usages(*, promo_id: int, page: int, limit: int) -> dict[str, object]:
    async with SessionLocal.begin() as session:
        rows = await AdminRuntimePromoRepo.list_redemptions(
            session,
            promo_id=promo_id,
            page=page,
            limit=limit,
        )
        total = await AdminRuntimePromoRepo.count_redemptions(session, promo_id=promo_id)

    pagination = build_pagination(total=total, page=page, limit=limit)
    return {
        "items": [
            {
                "id": str(item.id),
                "user_id": int(item.user_id),
                "status": item.status,
                "used_at": (item.applied_at or item.updated_at or item.created_at).isoformat(),
            }
            for item in rows
        ],
        "total": pagination["total"],
        "page": pagination["page"],
        "pages": pagination["pages"],
    }
