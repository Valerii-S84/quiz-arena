from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.core.config import get_settings as _get_settings

from .internal_referrals_handlers import (
    apply_referral_review_decision as _apply_referral_review_decision,
)
from .internal_referrals_handlers import get_referrals_dashboard as _get_referrals_dashboard
from .internal_referrals_handlers import (
    get_referrals_notification_events as _get_referrals_notification_events,
)
from .internal_referrals_handlers import get_referrals_review_queue as _get_referrals_review_queue
from .internal_referrals_models import (
    ReferralDashboardResponse,
    ReferralNotificationsFeedResponse,
    ReferralReviewActionRequest,
    ReferralReviewActionResponse,
    ReferralReviewQueueResponse,
)

router = APIRouter(tags=["internal", "referrals"])
get_settings = _get_settings

__all__ = ["get_settings", "router"]


@router.get("/internal/referrals/dashboard", response_model=ReferralDashboardResponse)
async def get_referrals_dashboard(
    request: Request,
    window_hours: int = Query(default=24, ge=1, le=168),
) -> ReferralDashboardResponse:
    return await _get_referrals_dashboard(request=request, window_hours=window_hours)


@router.get("/internal/referrals/review-queue", response_model=ReferralReviewQueueResponse)
async def get_referrals_review_queue(
    request: Request,
    window_hours: int = Query(default=72, ge=1, le=720),
    status: str | None = Query(default="REJECTED_FRAUD", min_length=1, max_length=24),
    limit: int = Query(default=100, ge=1, le=300),
) -> ReferralReviewQueueResponse:
    return await _get_referrals_review_queue(
        request=request,
        window_hours=window_hours,
        status=status,
        limit=limit,
    )


@router.post(
    "/internal/referrals/{referral_id}/review",
    response_model=ReferralReviewActionResponse,
)
async def apply_referral_review_decision(
    referral_id: int,
    payload: ReferralReviewActionRequest,
    request: Request,
) -> ReferralReviewActionResponse:
    return await _apply_referral_review_decision(
        referral_id=referral_id,
        payload=payload,
        request=request,
    )


@router.get("/internal/referrals/events", response_model=ReferralNotificationsFeedResponse)
async def get_referrals_notification_events(
    request: Request,
    window_hours: int = Query(default=168, ge=1, le=720),
    event_type: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=200, ge=1, le=500),
) -> ReferralNotificationsFeedResponse:
    return await _get_referrals_notification_events(
        request=request,
        window_hours=window_hours,
        event_type=event_type,
        limit=limit,
    )
