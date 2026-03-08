from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.routes.admin.deps import AdminPrincipal, add_admin_noindex_header, get_current_admin

from .promo_handlers import (
    check_promo_code as _check_promo_code,
    create_bulk_promos as _create_bulk_promos,
    create_promo as _create_promo,
    export_promos as _export_promos,
    get_promo as _get_promo,
    get_promo_stats as _get_promo_stats,
    list_promo_audit as _list_promo_audit,
    list_promo_products as _list_promo_products,
    list_promo_usages as _list_promo_usages,
    list_promos as _list_promos,
    patch_promo as _patch_promo,
    revoke_promo as _revoke_promo,
    toggle_promo as _toggle_promo,
)
from .promo_models import (
    PromoBulkCreateRequest,
    PromoCreateRequest,
    PromoPatchRequest,
    PromoRevokeRequest,
)

router = APIRouter(prefix="/admin/promo", tags=["admin-promo"])


@router.get("")
async def list_promos(
    response: Response,
    status: str | None = Query(default=None),
    query: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _list_promos(status=status, query=query, page=page, limit=limit)


@router.get("/products")
async def list_promo_products(
    response: Response,
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _list_promo_products()


@router.get("/check-code")
async def check_promo_code(
    response: Response,
    code: str = Query(min_length=1, max_length=64),
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _check_promo_code(code=code)


@router.post("")
async def create_promo(
    payload: PromoCreateRequest,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _create_promo(payload=payload, admin=admin)


@router.post("/bulk")
async def create_bulk_promos(
    payload: PromoBulkCreateRequest,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _create_bulk_promos(payload=payload, admin=admin)


@router.post("/bulk-generate")
async def bulk_generate_promos(
    payload: PromoBulkCreateRequest,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _create_bulk_promos(payload=payload, admin=admin)


@router.get("/export")
async def export_promos(
    response: Response,
    format: str = Query(default="csv"),
    _admin: AdminPrincipal = Depends(get_current_admin),
):
    add_admin_noindex_header(response)
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail={"code": "E_UNSUPPORTED_EXPORT_FORMAT"})
    return await _export_promos()


@router.get("/{promo_id}")
async def get_promo(
    promo_id: int,
    response: Response,
    reveal: bool = Query(default=False),
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _get_promo(promo_id=promo_id, admin=admin, reveal=reveal)


@router.get("/{promo_id}/stats")
async def get_promo_stats(
    promo_id: int,
    response: Response,
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _get_promo_stats(promo_id=promo_id)


@router.get("/{promo_id}/audit")
async def list_promo_audit(
    promo_id: int,
    response: Response,
    limit: int = Query(default=100, ge=1, le=200),
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _list_promo_audit(promo_id=promo_id, limit=limit)


@router.patch("/{promo_id}")
async def patch_promo(
    promo_id: int,
    payload: PromoPatchRequest,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _patch_promo(promo_id=promo_id, payload=payload, admin=admin)


@router.patch("/{promo_id}/toggle")
async def toggle_promo(
    promo_id: int,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _toggle_promo(promo_id=promo_id, admin=admin)


@router.post("/{promo_id}/revoke")
async def revoke_promo(
    promo_id: int,
    response: Response,
    payload: PromoRevokeRequest | None = None,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _revoke_promo(promo_id=promo_id, payload=payload, admin=admin)


@router.get("/{promo_id}/usages")
async def list_promo_usages(
    promo_id: int,
    response: Response,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)
    return await _list_promo_usages(promo_id=promo_id, page=page, limit=limit)
