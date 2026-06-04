from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response

from app.api.routes.admin.deps import AdminPrincipal, add_admin_noindex_header, get_current_admin
from app.api.routes.website_analytics_models import WebsiteAnalyticsOverviewResponse
from app.services.website_analytics_overview import build_website_analytics_overview

router = APIRouter(prefix="/admin", tags=["admin-website-analytics"])


@router.get("/website-analytics/overview", response_model=WebsiteAnalyticsOverviewResponse)
async def get_website_analytics_overview(
    response: Response,
    days: int = Query(default=7, ge=1, le=90),
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> WebsiteAnalyticsOverviewResponse:
    add_admin_noindex_header(response)
    return await build_website_analytics_overview(
        days=days,
        now_utc=datetime.now(timezone.utc),
    )
