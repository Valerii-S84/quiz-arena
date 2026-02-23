from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.core.config import get_settings as _get_settings

from .internal_promo_handlers import get_promo_dashboard as _get_promo_dashboard
from .internal_promo_handlers import list_promo_campaigns as _list_promo_campaigns
from .internal_promo_handlers import redeem_promo as _redeem_promo
from .internal_promo_handlers import rollback_promo_for_refund as _rollback_promo_for_refund
from .internal_promo_handlers import update_promo_campaign_status as _update_promo_campaign_status
from .internal_promo_models import (
    PromoCampaignListResponse,
    PromoCampaignResponse,
    PromoCampaignStatusUpdateRequest,
    PromoDashboardResponse,
    PromoRedeemRequest,
    PromoRedeemResponse,
    PromoRefundRollbackRequest,
    PromoRefundRollbackResponse,
)

router = APIRouter(tags=["internal", "promo"])
get_settings = _get_settings

__all__ = ["get_settings", "router"]


@router.post("/internal/promo/redeem", response_model=PromoRedeemResponse)
async def redeem_promo(payload: PromoRedeemRequest, request: Request) -> PromoRedeemResponse:
    return await _redeem_promo(payload=payload, request=request)


@router.get("/internal/promo/dashboard", response_model=PromoDashboardResponse)
async def get_promo_dashboard(
    request: Request,
    window_hours: int = Query(default=24, ge=1, le=168),
) -> PromoDashboardResponse:
    return await _get_promo_dashboard(request=request, window_hours=window_hours)


@router.get("/internal/promo/campaigns", response_model=PromoCampaignListResponse)
async def list_promo_campaigns(
    request: Request,
    status: str | None = Query(default=None, min_length=1, max_length=16),
    campaign_name: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
) -> PromoCampaignListResponse:
    return await _list_promo_campaigns(
        request=request,
        status=status,
        campaign_name=campaign_name,
        limit=limit,
    )


@router.post(
    "/internal/promo/campaigns/{promo_code_id}/status",
    response_model=PromoCampaignResponse,
)
async def update_promo_campaign_status(
    promo_code_id: int,
    payload: PromoCampaignStatusUpdateRequest,
    request: Request,
) -> PromoCampaignResponse:
    return await _update_promo_campaign_status(
        promo_code_id=promo_code_id,
        payload=payload,
        request=request,
    )


@router.post("/internal/promo/refund-rollback", response_model=PromoRefundRollbackResponse)
async def rollback_promo_for_refund(
    payload: PromoRefundRollbackRequest,
    request: Request,
) -> PromoRefundRollbackResponse:
    return await _rollback_promo_for_refund(payload=payload, request=request)
