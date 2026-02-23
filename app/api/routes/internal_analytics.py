from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.db.repo.analytics_repo import AnalyticsRepo
from app.db.session import SessionLocal
from app.economy.energy.constants import BERLIN_TIMEZONE
from app.services.analytics_daily import build_daily_snapshot
from app.services.internal_auth import (
    extract_client_ip,
    is_client_ip_allowed,
    is_internal_request_authenticated,
)

router = APIRouter(tags=["internal", "analytics"])
logger = structlog.get_logger(__name__)


class AnalyticsDailyKpiResponse(BaseModel):
    local_date_berlin: date
    dau: int = Field(ge=0)
    wau: int = Field(ge=0)
    mau: int = Field(ge=0)
    purchases_credited_total: int = Field(ge=0)
    purchasers_total: int = Field(ge=0)
    purchase_rate: float = Field(ge=0.0, le=1.0)
    promo_redemptions_total: int = Field(ge=0)
    promo_redemptions_applied_total: int = Field(ge=0)
    promo_redemption_rate: float = Field(ge=0.0, le=1.0)
    promo_to_paid_conversions_total: int = Field(ge=0)
    quiz_sessions_started_total: int = Field(ge=0)
    quiz_sessions_completed_total: int = Field(ge=0)
    gameplay_completion_rate: float = Field(ge=0.0, le=1.0)
    energy_zero_events_total: int = Field(ge=0)
    streak_lost_events_total: int = Field(ge=0)
    referral_reward_milestone_events_total: int = Field(ge=0)
    referral_reward_granted_events_total: int = Field(ge=0)
    purchase_init_events_total: int = Field(ge=0)
    purchase_invoice_sent_events_total: int = Field(ge=0)
    purchase_precheckout_ok_events_total: int = Field(ge=0)
    purchase_paid_uncredited_events_total: int = Field(ge=0)
    purchase_credited_events_total: int = Field(ge=0)
    calculated_at: datetime


class InternalAnalyticsDashboardResponse(BaseModel):
    generated_at: datetime
    days: int = Field(ge=1, le=90)
    rows: list[AnalyticsDailyKpiResponse]


def _assert_internal_access(request: Request) -> None:
    settings = get_settings()
    client_ip = extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )

    if not is_client_ip_allowed(client_ip=client_ip, allowlist=settings.internal_api_allowlist):
        logger.warning(
            "internal_analytics_auth_failed",
            reason="ip_not_allowed",
            client_ip=client_ip,
        )
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})

    if not is_internal_request_authenticated(
        request,
        expected_token=settings.internal_api_token,
    ):
        logger.warning(
            "internal_analytics_auth_failed",
            reason="invalid_credentials",
            client_ip=client_ip,
        )
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})


def _as_row(item: object) -> AnalyticsDailyKpiResponse:
    return AnalyticsDailyKpiResponse(
        local_date_berlin=getattr(item, "local_date_berlin"),
        dau=int(getattr(item, "dau")),
        wau=int(getattr(item, "wau")),
        mau=int(getattr(item, "mau")),
        purchases_credited_total=int(getattr(item, "purchases_credited_total")),
        purchasers_total=int(getattr(item, "purchasers_total")),
        purchase_rate=float(getattr(item, "purchase_rate")),
        promo_redemptions_total=int(getattr(item, "promo_redemptions_total")),
        promo_redemptions_applied_total=int(getattr(item, "promo_redemptions_applied_total")),
        promo_redemption_rate=float(getattr(item, "promo_redemption_rate")),
        promo_to_paid_conversions_total=int(getattr(item, "promo_to_paid_conversions_total")),
        quiz_sessions_started_total=int(getattr(item, "quiz_sessions_started_total")),
        quiz_sessions_completed_total=int(getattr(item, "quiz_sessions_completed_total")),
        gameplay_completion_rate=float(getattr(item, "gameplay_completion_rate")),
        energy_zero_events_total=int(getattr(item, "energy_zero_events_total")),
        streak_lost_events_total=int(getattr(item, "streak_lost_events_total")),
        referral_reward_milestone_events_total=int(
            getattr(item, "referral_reward_milestone_events_total")
        ),
        referral_reward_granted_events_total=int(
            getattr(item, "referral_reward_granted_events_total")
        ),
        purchase_init_events_total=int(getattr(item, "purchase_init_events_total")),
        purchase_invoice_sent_events_total=int(getattr(item, "purchase_invoice_sent_events_total")),
        purchase_precheckout_ok_events_total=int(
            getattr(item, "purchase_precheckout_ok_events_total")
        ),
        purchase_paid_uncredited_events_total=int(
            getattr(item, "purchase_paid_uncredited_events_total")
        ),
        purchase_credited_events_total=int(getattr(item, "purchase_credited_events_total")),
        calculated_at=getattr(item, "calculated_at"),
    )


@router.get("/internal/analytics/executive", response_model=InternalAnalyticsDashboardResponse)
async def get_internal_analytics_executive(
    request: Request,
    days: int = Query(default=30, ge=1, le=90),
) -> InternalAnalyticsDashboardResponse:
    _assert_internal_access(request)
    now_utc = datetime.now(timezone.utc)

    async with SessionLocal.begin() as session:
        rows = await AnalyticsRepo.list_daily(session, limit=days)
        if not rows:
            today_berlin = now_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()
            snapshot = await build_daily_snapshot(
                session,
                local_date_berlin=today_berlin,
                now_utc=now_utc,
            )
            await AnalyticsRepo.upsert_daily(session, row=snapshot.row)
            rows = await AnalyticsRepo.list_daily(session, limit=days)

    return InternalAnalyticsDashboardResponse(
        generated_at=now_utc,
        days=days,
        rows=[_as_row(row) for row in rows],
    )
