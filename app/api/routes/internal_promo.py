from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.db.repo.promo_repo import PromoRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.session import SessionLocal
from app.economy.promo.errors import (
    PromoAlreadyUsedError,
    PromoExpiredError,
    PromoIdempotencyConflictError,
    PromoInvalidError,
    PromoNotApplicableError,
    PromoRateLimitedError,
    PromoUserNotFoundError,
)
from app.economy.promo.service import PromoService
from app.economy.promo.types import PromoRedeemResult
from app.services.internal_auth import (
    extract_client_ip,
    is_client_ip_allowed,
    is_internal_request_authenticated,
)

router = APIRouter(tags=["internal", "promo"])
logger = structlog.get_logger(__name__)
PROMO_FAILURE_RESULTS = ("INVALID", "EXPIRED", "NOT_APPLICABLE", "RATE_LIMITED")
PROMO_GUARD_LOOKBACK_MINUTES = 10
PROMO_GUARD_MIN_FAILED_ATTEMPTS = 100
PROMO_GUARD_MIN_DISTINCT_USERS = 2
PROMO_CAMPAIGN_STATUSES = {"ACTIVE", "PAUSED", "EXPIRED", "DEPLETED"}
PROMO_MUTABLE_CAMPAIGN_STATUSES = {"ACTIVE", "PAUSED"}
PROMO_ALLOWED_STATUS_TRANSITIONS = {("ACTIVE", "PAUSED"), ("PAUSED", "ACTIVE")}
REFUNDABLE_PURCHASE_STATUSES = {"CREDITED", "PAID_UNCREDITED"}


class PromoRedeemRequest(BaseModel):
    user_id: int = Field(gt=0)
    promo_code: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=96)


class PromoRedeemResponse(BaseModel):
    redemption_id: UUID
    result_type: str
    premium_days: int | None = None
    premium_ends_at: datetime | None = None
    discount_percent: int | None = None
    reserved_until: datetime | None = None
    target_scope: str | None = None


class PromoDashboardResponse(BaseModel):
    generated_at: datetime
    window_hours: int = Field(ge=1, le=168)
    attempts_total: int = Field(ge=0)
    attempts_accepted: int = Field(ge=0)
    attempts_failed: int = Field(ge=0)
    acceptance_rate: float = Field(ge=0.0, le=1.0)
    failure_rate: float = Field(ge=0.0, le=1.0)
    attempt_failures_by_result: dict[str, int]
    redemptions_total: int = Field(ge=0)
    redemptions_applied: int = Field(ge=0)
    redemptions_by_status: dict[str, int]
    discount_redemptions_total: int = Field(ge=0)
    discount_redemptions_applied: int = Field(ge=0)
    discount_redemptions_reserved: int = Field(ge=0)
    discount_redemptions_expired: int = Field(ge=0)
    discount_conversion_rate: float = Field(ge=0.0, le=1.0)
    guard_window_minutes: int = Field(ge=1)
    guard_trigger_hashes: int = Field(ge=0)
    active_campaigns_total: int = Field(ge=0)
    paused_campaigns_total: int = Field(ge=0)
    paused_campaigns_recent: int = Field(ge=0)


class PromoCampaignResponse(BaseModel):
    id: int
    campaign_name: str
    promo_type: str
    target_scope: str
    status: str
    valid_from: datetime
    valid_until: datetime
    max_total_uses: int | None = None
    used_total: int = Field(ge=0)
    updated_at: datetime


class PromoCampaignStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=16)
    reason: str | None = Field(default=None, max_length=256)
    expected_current_status: str | None = Field(default=None, max_length=16)


class PromoCampaignListResponse(BaseModel):
    campaigns: list[PromoCampaignResponse]


class PromoRefundRollbackRequest(BaseModel):
    purchase_id: UUID
    reason: str | None = Field(default=None, max_length=256)


class PromoRefundRollbackResponse(BaseModel):
    purchase_id: UUID
    purchase_status: str
    promo_redemption_id: UUID | None = None
    promo_redemption_status: str | None = None
    promo_code_id: int | None = None
    promo_code_used_total: int | None = None
    idempotent_replay: bool


def _as_response(result: PromoRedeemResult) -> PromoRedeemResponse:
    return PromoRedeemResponse(
        redemption_id=result.redemption_id,
        result_type=result.result_type,
        premium_days=result.premium_days,
        premium_ends_at=result.premium_ends_at,
        discount_percent=result.discount_percent,
        reserved_until=result.reserved_until,
        target_scope=result.target_scope,
    )


def _campaign_as_response(campaign: object) -> PromoCampaignResponse:
    return PromoCampaignResponse(
        id=int(getattr(campaign, "id")),
        campaign_name=str(getattr(campaign, "campaign_name")),
        promo_type=str(getattr(campaign, "promo_type")),
        target_scope=str(getattr(campaign, "target_scope")),
        status=str(getattr(campaign, "status")),
        valid_from=getattr(campaign, "valid_from"),
        valid_until=getattr(campaign, "valid_until"),
        max_total_uses=getattr(campaign, "max_total_uses"),
        used_total=int(getattr(campaign, "used_total")),
        updated_at=getattr(campaign, "updated_at"),
    )


def _safe_rate(*, numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _assert_internal_access(request: Request) -> None:
    settings = get_settings()
    client_ip = extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )

    if not is_client_ip_allowed(client_ip=client_ip, allowlist=settings.internal_api_allowlist):
        logger.warning("internal_promo_auth_failed", reason="ip_not_allowed", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})

    if not is_internal_request_authenticated(
        request,
        expected_token=settings.internal_api_token,
    ):
        logger.warning(
            "internal_promo_auth_failed",
            reason="invalid_credentials",
            client_ip=client_ip,
        )
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})


@router.post("/internal/promo/redeem", response_model=PromoRedeemResponse)
async def redeem_promo(payload: PromoRedeemRequest, request: Request) -> PromoRedeemResponse:
    _assert_internal_access(request)

    now_utc = datetime.now(timezone.utc)
    try:
        async with SessionLocal.begin() as session:
            result = await PromoService.redeem(
                session,
                user_id=payload.user_id,
                promo_code=payload.promo_code,
                idempotency_key=payload.idempotency_key,
                now_utc=now_utc,
            )
    except (PromoInvalidError, PromoUserNotFoundError) as exc:
        raise HTTPException(status_code=404, detail={"code": "E_PROMO_INVALID"}) from exc
    except PromoExpiredError as exc:
        raise HTTPException(status_code=410, detail={"code": "E_PROMO_EXPIRED"}) from exc
    except (PromoAlreadyUsedError, PromoIdempotencyConflictError) as exc:
        raise HTTPException(status_code=409, detail={"code": "E_PROMO_ALREADY_USED"}) from exc
    except PromoNotApplicableError as exc:
        raise HTTPException(status_code=422, detail={"code": "E_PROMO_NOT_APPLICABLE"}) from exc
    except PromoRateLimitedError as exc:
        raise HTTPException(status_code=429, detail={"code": "E_PROMO_RATE_LIMITED"}) from exc

    return _as_response(result)


@router.get("/internal/promo/dashboard", response_model=PromoDashboardResponse)
async def get_promo_dashboard(
    request: Request,
    window_hours: int = Query(default=24, ge=1, le=168),
) -> PromoDashboardResponse:
    _assert_internal_access(request)

    now_utc = datetime.now(timezone.utc)
    window_since_utc = now_utc - timedelta(hours=window_hours)
    guard_since_utc = now_utc - timedelta(minutes=PROMO_GUARD_LOOKBACK_MINUTES)

    async with SessionLocal.begin() as session:
        attempt_counts = await PromoRepo.count_attempts_by_result(
            session, since_utc=window_since_utc
        )
        redemption_counts = await PromoRepo.count_redemptions_by_status(
            session, since_utc=window_since_utc
        )
        discount_redemption_counts = await PromoRepo.count_discount_redemptions_by_status(
            session,
            since_utc=window_since_utc,
        )
        campaign_counts = await PromoRepo.count_campaigns_by_status(session)
        paused_recent = await PromoRepo.count_paused_campaigns_since(
            session, since_utc=window_since_utc
        )
        guard_trigger_hashes = await PromoRepo.count_abusive_code_hashes(
            session,
            since_utc=guard_since_utc,
            min_failed_attempts=PROMO_GUARD_MIN_FAILED_ATTEMPTS,
            min_distinct_users=PROMO_GUARD_MIN_DISTINCT_USERS,
        )

    attempts_total = sum(attempt_counts.values())
    attempts_accepted = attempt_counts.get("ACCEPTED", 0)
    attempts_failed = max(0, attempts_total - attempts_accepted)

    redemptions_total = sum(redemption_counts.values())
    redemptions_applied = redemption_counts.get("APPLIED", 0)

    discount_redemptions_total = sum(discount_redemption_counts.values())
    discount_redemptions_applied = discount_redemption_counts.get("APPLIED", 0)
    discount_redemptions_reserved = discount_redemption_counts.get("RESERVED", 0)
    discount_redemptions_expired = discount_redemption_counts.get("EXPIRED", 0)

    return PromoDashboardResponse(
        generated_at=now_utc,
        window_hours=window_hours,
        attempts_total=attempts_total,
        attempts_accepted=attempts_accepted,
        attempts_failed=attempts_failed,
        acceptance_rate=_safe_rate(numerator=attempts_accepted, denominator=attempts_total),
        failure_rate=_safe_rate(numerator=attempts_failed, denominator=attempts_total),
        attempt_failures_by_result={
            result: attempt_counts.get(result, 0) for result in PROMO_FAILURE_RESULTS
        },
        redemptions_total=redemptions_total,
        redemptions_applied=redemptions_applied,
        redemptions_by_status=redemption_counts,
        discount_redemptions_total=discount_redemptions_total,
        discount_redemptions_applied=discount_redemptions_applied,
        discount_redemptions_reserved=discount_redemptions_reserved,
        discount_redemptions_expired=discount_redemptions_expired,
        discount_conversion_rate=_safe_rate(
            numerator=discount_redemptions_applied,
            denominator=discount_redemptions_total,
        ),
        guard_window_minutes=PROMO_GUARD_LOOKBACK_MINUTES,
        guard_trigger_hashes=guard_trigger_hashes,
        active_campaigns_total=campaign_counts.get("ACTIVE", 0),
        paused_campaigns_total=campaign_counts.get("PAUSED", 0),
        paused_campaigns_recent=paused_recent,
    )


@router.get("/internal/promo/campaigns", response_model=PromoCampaignListResponse)
async def list_promo_campaigns(
    request: Request,
    status: str | None = Query(default=None, min_length=1, max_length=16),
    campaign_name: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
) -> PromoCampaignListResponse:
    _assert_internal_access(request)
    normalized_status: str | None = status.strip().upper() if status is not None else None
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


@router.post(
    "/internal/promo/campaigns/{promo_code_id}/status",
    response_model=PromoCampaignResponse,
)
async def update_promo_campaign_status(
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


@router.post("/internal/promo/refund-rollback", response_model=PromoRefundRollbackResponse)
async def rollback_promo_for_refund(
    payload: PromoRefundRollbackRequest,
    request: Request,
) -> PromoRefundRollbackResponse:
    _assert_internal_access(request)
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id_for_update(session, payload.purchase_id)
        if purchase is None:
            raise HTTPException(status_code=404, detail={"code": "E_PURCHASE_NOT_FOUND"})

        redemption = None
        promo_code = None
        rollback_applied = False

        if purchase.status == "REFUNDED":
            if purchase.applied_promo_code_id is not None:
                redemption, promo_code, rollback_applied = (
                    await PromoRepo.revoke_redemption_for_refund(
                        session,
                        purchase_id=purchase.id,
                        promo_code_id=purchase.applied_promo_code_id,
                        now_utc=now_utc,
                    )
                )
            return PromoRefundRollbackResponse(
                purchase_id=purchase.id,
                purchase_status=purchase.status,
                promo_redemption_id=None if redemption is None else redemption.id,
                promo_redemption_status=(None if redemption is None else redemption.status),
                promo_code_id=purchase.applied_promo_code_id,
                promo_code_used_total=(None if promo_code is None else promo_code.used_total),
                idempotent_replay=not rollback_applied,
            )

        if purchase.status not in REFUNDABLE_PURCHASE_STATUSES:
            raise HTTPException(status_code=409, detail={"code": "E_PURCHASE_REFUND_NOT_ALLOWED"})

        purchase.status = "REFUNDED"
        purchase.refunded_at = now_utc

        if purchase.applied_promo_code_id is not None:
            redemption, promo_code, rollback_applied = await PromoRepo.revoke_redemption_for_refund(
                session,
                purchase_id=purchase.id,
                promo_code_id=purchase.applied_promo_code_id,
                now_utc=now_utc,
            )

        logger.info(
            "internal_promo_refund_rollback_applied",
            purchase_id=str(purchase.id),
            promo_code_id=purchase.applied_promo_code_id,
            promo_redemption_id=None if redemption is None else str(redemption.id),
            reason=(payload.reason or "").strip() or None,
        )
        return PromoRefundRollbackResponse(
            purchase_id=purchase.id,
            purchase_status=purchase.status,
            promo_redemption_id=None if redemption is None else redemption.id,
            promo_redemption_status=None if redemption is None else redemption.status,
            promo_code_id=purchase.applied_promo_code_id,
            promo_code_used_total=None if promo_code is None else promo_code.used_total,
            idempotent_replay=False,
        )
