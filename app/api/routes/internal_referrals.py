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
from app.services.referrals_observability import (
    build_referrals_dashboard_snapshot,
    evaluate_referrals_alert_state,
    get_referrals_alert_thresholds,
)

router = APIRouter(tags=["internal", "referrals"])
logger = structlog.get_logger(__name__)


class ReferralTopReferrerStatsResponse(BaseModel):
    referrer_user_id: int = Field(gt=0)
    started_total: int = Field(ge=0)
    rejected_fraud_total: int = Field(ge=0)
    rejected_fraud_rate: float = Field(ge=0.0, le=1.0)
    last_start_at: datetime | None = None


class ReferralFraudCaseResponse(BaseModel):
    referral_id: int = Field(gt=0)
    referrer_user_id: int = Field(gt=0)
    referred_user_id: int = Field(gt=0)
    fraud_score: float = Field(ge=0.0)
    status: str
    created_at: datetime


class ReferralDashboardThresholdsResponse(BaseModel):
    min_started: int = Field(ge=0)
    max_fraud_rejected_rate: float = Field(ge=0.0, le=1.0)
    max_rejected_fraud_total: int = Field(ge=0)
    max_referrer_rejected_fraud: int = Field(ge=0)


class ReferralDashboardAlertsResponse(BaseModel):
    thresholds_applied: bool
    fraud_spike_detected: bool
    fraud_rate_above_threshold: bool
    rejected_fraud_total_above_threshold: bool
    referrer_spike_detected: bool


class ReferralDashboardResponse(BaseModel):
    generated_at: datetime
    window_hours: int = Field(ge=1, le=168)
    referrals_started_total: int = Field(ge=0)
    qualified_like_total: int = Field(ge=0)
    rewarded_total: int = Field(ge=0)
    rejected_fraud_total: int = Field(ge=0)
    canceled_total: int = Field(ge=0)
    qualification_rate: float = Field(ge=0.0, le=1.0)
    reward_rate: float = Field(ge=0.0, le=1.0)
    fraud_rejected_rate: float = Field(ge=0.0, le=1.0)
    status_counts: dict[str, int]
    top_referrers: list[ReferralTopReferrerStatsResponse]
    recent_fraud_cases: list[ReferralFraudCaseResponse]
    thresholds: ReferralDashboardThresholdsResponse
    alerts: ReferralDashboardAlertsResponse


def _assert_internal_access(request: Request) -> None:
    settings = get_settings()
    client_ip = extract_client_ip(request)
    token = request.headers.get("X-Internal-Token")

    if not is_valid_internal_token(
        expected_token=settings.internal_api_token,
        received_token=token,
    ):
        logger.warning("internal_referrals_auth_failed", reason="invalid_token", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})

    if not is_client_ip_allowed(client_ip=client_ip, allowlist=settings.internal_api_allowlist):
        logger.warning("internal_referrals_auth_failed", reason="ip_not_allowed", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})


@router.get("/internal/referrals/dashboard", response_model=ReferralDashboardResponse)
async def get_referrals_dashboard(
    request: Request,
    window_hours: int = Query(default=24, ge=1, le=168),
) -> ReferralDashboardResponse:
    _assert_internal_access(request)
    now_utc = datetime.now(timezone.utc)
    settings = get_settings()
    thresholds = get_referrals_alert_thresholds(settings)

    async with SessionLocal.begin() as session:
        snapshot = await build_referrals_dashboard_snapshot(
            session,
            now_utc=now_utc,
            window_hours=window_hours,
        )

    alert_state = evaluate_referrals_alert_state(snapshot=snapshot, thresholds=thresholds)
    return ReferralDashboardResponse(
        generated_at=snapshot.generated_at,
        window_hours=snapshot.window_hours,
        referrals_started_total=snapshot.referrals_started_total,
        qualified_like_total=snapshot.qualified_like_total,
        rewarded_total=snapshot.rewarded_total,
        rejected_fraud_total=snapshot.rejected_fraud_total,
        canceled_total=snapshot.canceled_total,
        qualification_rate=snapshot.qualification_rate,
        reward_rate=snapshot.reward_rate,
        fraud_rejected_rate=snapshot.fraud_rejected_rate,
        status_counts=snapshot.status_counts,
        top_referrers=[
            ReferralTopReferrerStatsResponse(**row) for row in snapshot.top_referrers
        ],
        recent_fraud_cases=[
            ReferralFraudCaseResponse(**row) for row in snapshot.recent_fraud_cases
        ],
        thresholds=ReferralDashboardThresholdsResponse(
            min_started=thresholds.min_started,
            max_fraud_rejected_rate=thresholds.max_fraud_rejected_rate,
            max_rejected_fraud_total=thresholds.max_rejected_fraud_total,
            max_referrer_rejected_fraud=thresholds.max_referrer_rejected_fraud,
        ),
        alerts=ReferralDashboardAlertsResponse(
            thresholds_applied=alert_state.thresholds_applied,
            fraud_spike_detected=alert_state.fraud_spike_detected,
            fraud_rate_above_threshold=alert_state.fraud_rate_above_threshold,
            rejected_fraud_total_above_threshold=alert_state.rejected_fraud_total_above_threshold,
            referrer_spike_detected=alert_state.referrer_spike_detected,
        ),
    )
