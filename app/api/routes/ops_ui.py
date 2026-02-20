from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

from app.core.config import get_settings
from app.services.internal_auth import extract_client_ip, is_client_ip_allowed

router = APIRouter(tags=["ops-ui"])
logger = structlog.get_logger(__name__)

OPS_UI_ROOT = Path(__file__).resolve().parents[2] / "ops_ui" / "site"
OPS_UI_STATIC_DIR = OPS_UI_ROOT / "static"
OPS_UI_PAGES = {
    "promo": OPS_UI_ROOT / "promo.html",
    "referrals": OPS_UI_ROOT / "referrals.html",
    "notifications": OPS_UI_ROOT / "notifications.html",
}


def _assert_internal_ip_access(request: Request) -> None:
    settings = get_settings()
    client_ip = extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )
    if not is_client_ip_allowed(client_ip=client_ip, allowlist=settings.internal_api_allowlist):
        logger.warning("ops_ui_auth_failed", reason="ip_not_allowed", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})


def _render_page(request: Request, *, page_name: str) -> FileResponse:
    _assert_internal_ip_access(request)
    page_path = OPS_UI_PAGES[page_name]
    if not page_path.exists():
        raise HTTPException(status_code=503, detail={"code": "E_OPS_UI_ASSET_MISSING"})
    return FileResponse(path=page_path, media_type="text/html")


@router.get("/ops")
async def get_ops_root() -> RedirectResponse:
    return RedirectResponse(url="/ops/promo", status_code=307)


@router.get("/ops/promo")
async def get_ops_promo_page(request: Request) -> FileResponse:
    return _render_page(request, page_name="promo")


@router.get("/ops/referrals")
async def get_ops_referrals_page(request: Request) -> FileResponse:
    return _render_page(request, page_name="referrals")


@router.get("/ops/notifications")
async def get_ops_notifications_page(request: Request) -> FileResponse:
    return _render_page(request, page_name="notifications")
