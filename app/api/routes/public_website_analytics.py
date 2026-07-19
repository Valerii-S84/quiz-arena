from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.routes.website_analytics_models import WebsiteAnalyticsEventPayload
from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.services.website_analytics_ingest import (
    build_website_event,
    is_website_analytics_rate_limited,
)

router = APIRouter(tags=["public-site", "website-analytics"])


@router.post("/public/website-analytics/events", status_code=status.HTTP_204_NO_CONTENT)
@router.post("/api/public/website-analytics/events", status_code=status.HTTP_204_NO_CONTENT)
async def ingest_website_analytics_event(
    payload: WebsiteAnalyticsEventPayload,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    if await is_website_analytics_rate_limited(request, settings):
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    event = build_website_event(
        payload,
        settings=settings,
        now_utc=datetime.now(timezone.utc),
    )
    if event is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    async with SessionLocal.begin() as session:
        session.add(event)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
