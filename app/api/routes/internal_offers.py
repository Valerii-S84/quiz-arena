from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.internal_auth import (
    extract_client_ip,
    is_client_ip_allowed,
    is_valid_internal_token,
)
from app.services.offers_observability import (
    build_offer_funnel_snapshot,
    evaluate_offer_alert_state,
    get_offer_alert_thresholds,
)

router = APIRouter(tags=["internal", "offers"])
logger = structlog.get_logger(__name__)


class OfferDashboardThresholdsResponse(BaseModel):
    min_impressions: int = Field(ge=0)
    min_conversion_rate: float = Field(ge=0.0, le=1.0)
    max_dismiss_rate: float = Field(ge=0.0, le=1.0)
    max_impressions_per_user: float = Field(ge=0.0)


class OfferDashboardAlertsResponse(BaseModel):
    thresholds_applied: bool
    conversion_drop_detected: bool
    spam_anomaly_detected: bool
    conversion_rate_below_threshold: bool
    dismiss_rate_above_threshold: bool
    impressions_per_user_above_threshold: bool


class OfferDashboardResponse(BaseModel):
    generated_at: datetime
    window_hours: int = Field(ge=1, le=168)
    impressions_total: int = Field(ge=0)
    unique_users: int = Field(ge=0)
    clicks_total: int = Field(ge=0)
    dismissals_total: int = Field(ge=0)
    conversions_total: int = Field(ge=0)
    click_through_rate: float = Field(ge=0.0, le=1.0)
    conversion_rate: float = Field(ge=0.0, le=1.0)
    dismiss_rate: float = Field(ge=0.0, le=1.0)
    impressions_per_user: float = Field(ge=0.0)
    top_offer_codes: dict[str, int]
    thresholds: OfferDashboardThresholdsResponse
    alerts: OfferDashboardAlertsResponse


def _assert_internal_access(request: Request) -> None:
    settings = get_settings()
    client_ip = extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )
    token = request.headers.get("X-Internal-Token")

    if not is_valid_internal_token(
        expected_token=settings.internal_api_token,
        received_token=token,
    ):
        logger.warning("internal_offers_auth_failed", reason="invalid_token", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})

    if not is_client_ip_allowed(client_ip=client_ip, allowlist=settings.internal_api_allowlist):
        logger.warning("internal_offers_auth_failed", reason="ip_not_allowed", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})


@router.get("/internal/offers/dashboard", response_model=OfferDashboardResponse)
async def get_offers_dashboard(
    request: Request,
    window_hours: int = Query(default=24, ge=1, le=168),
) -> OfferDashboardResponse:
    _assert_internal_access(request)
    now_utc = datetime.now(timezone.utc)
    settings = get_settings()
    thresholds = get_offer_alert_thresholds(settings)

    async with SessionLocal.begin() as session:
        snapshot = await build_offer_funnel_snapshot(
            session,
            now_utc=now_utc,
            window_hours=window_hours,
        )

    alert_state = evaluate_offer_alert_state(snapshot=snapshot, thresholds=thresholds)
    return OfferDashboardResponse(
        generated_at=snapshot.generated_at,
        window_hours=snapshot.window_hours,
        impressions_total=snapshot.impressions_total,
        unique_users=snapshot.unique_users,
        clicks_total=snapshot.clicks_total,
        dismissals_total=snapshot.dismissals_total,
        conversions_total=snapshot.conversions_total,
        click_through_rate=snapshot.click_through_rate,
        conversion_rate=snapshot.conversion_rate,
        dismiss_rate=snapshot.dismiss_rate,
        impressions_per_user=snapshot.impressions_per_user,
        top_offer_codes=snapshot.top_offer_codes,
        thresholds=OfferDashboardThresholdsResponse(
            min_impressions=thresholds.min_impressions,
            min_conversion_rate=thresholds.min_conversion_rate,
            max_dismiss_rate=thresholds.max_dismiss_rate,
            max_impressions_per_user=thresholds.max_impressions_per_user,
        ),
        alerts=OfferDashboardAlertsResponse(
            thresholds_applied=alert_state.thresholds_applied,
            conversion_drop_detected=alert_state.conversion_drop_detected,
            spam_anomaly_detected=alert_state.spam_anomaly_detected,
            conversion_rate_below_threshold=alert_state.conversion_rate_below_threshold,
            dismiss_rate_above_threshold=alert_state.dismiss_rate_above_threshold,
            impressions_per_user_above_threshold=alert_state.impressions_per_user_above_threshold,
        ),
    )
