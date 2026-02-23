from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, Request

from app.db.repo.promo_repo import PromoRepo
from app.db.session import SessionLocal

from .internal_promo_constants import (
    PROMO_ALLOWED_STATUS_TRANSITIONS,
    PROMO_CAMPAIGN_STATUSES,
    PROMO_MUTABLE_CAMPAIGN_STATUSES,
)
from .internal_promo_helpers import _assert_internal_access, _campaign_as_response
from .internal_promo_models import (
    PromoCampaignListResponse,
    PromoCampaignResponse,
    PromoCampaignStatusUpdateRequest,
)

logger = structlog.get_logger(__name__)


def _normalize_status(raw_status: str | None) -> str | None:
    if raw_status is None:
        return None
    return raw_status.strip().upper()


async def list_promo_campaigns(
    *,
    request: Request,
    status: str | None,
    campaign_name: str | None,
    limit: int,
) -> PromoCampaignListResponse:
    _assert_internal_access(request)
    normalized_status = _normalize_status(status)
    if normalized_status is not None and normalized_status not in PROMO_CAMPAIGN_STATUSES:
        raise HTTPException(status_code=422, detail={"code": "E_PROMO_STATUS_INVALID"})

    async with SessionLocal.begin() as session:
        campaigns = await PromoRepo.list_codes(
            session,
            status=normalized_status,
            campaign_name=campaign_name.strip() if campaign_name else None,
            limit=limit,
        )
    return PromoCampaignListResponse(
        campaigns=[_campaign_as_response(campaign) for campaign in campaigns]
    )


async def update_promo_campaign_status(
    *,
    promo_code_id: int,
    payload: PromoCampaignStatusUpdateRequest,
    request: Request,
) -> PromoCampaignResponse:
    _assert_internal_access(request)
    desired_status = payload.status.strip().upper()
    if desired_status not in PROMO_MUTABLE_CAMPAIGN_STATUSES:
        raise HTTPException(status_code=422, detail={"code": "E_PROMO_STATUS_INVALID"})

    expected_status: str | None = None
    if payload.expected_current_status is not None:
        expected_status = payload.expected_current_status.strip().upper()
        if expected_status not in PROMO_CAMPAIGN_STATUSES:
            raise HTTPException(status_code=422, detail={"code": "E_PROMO_STATUS_INVALID"})

    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        campaign = await PromoRepo.get_code_by_id_for_update(session, promo_code_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail={"code": "E_PROMO_NOT_FOUND"})
        if expected_status is not None and campaign.status != expected_status:
            raise HTTPException(status_code=409, detail={"code": "E_PROMO_STATUS_CONFLICT"})
        if (
            campaign.status not in PROMO_MUTABLE_CAMPAIGN_STATUSES
            and campaign.status != desired_status
        ):
            raise HTTPException(status_code=409, detail={"code": "E_PROMO_STATUS_CONFLICT"})
        if (
            campaign.status != desired_status
            and (campaign.status, desired_status) not in PROMO_ALLOWED_STATUS_TRANSITIONS
        ):
            raise HTTPException(status_code=409, detail={"code": "E_PROMO_STATUS_CONFLICT"})
        if campaign.status != desired_status:
            previous_status = campaign.status
            campaign.status = desired_status
            campaign.updated_at = now_utc
            logger.info(
                "internal_promo_campaign_status_changed",
                promo_code_id=promo_code_id,
                campaign_name=campaign.campaign_name,
                previous_status=previous_status,
                next_status=desired_status,
                reason=(payload.reason or "").strip() or None,
            )
        return _campaign_as_response(campaign)
