from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.db.repo.promo_repo import PromoRepo
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
    is_valid_internal_token,
)

router = APIRouter(tags=["internal", "promo"])
logger = structlog.get_logger(__name__)
PROMO_FAILURE_RESULTS = ("INVALID", "EXPIRED", "NOT_APPLICABLE", "RATE_LIMITED")
PROMO_GUARD_LOOKBACK_MINUTES = 10
PROMO_GUARD_MIN_FAILED_ATTEMPTS = 100
PROMO_GUARD_MIN_DISTINCT_USERS = 2


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


def _safe_rate(*, numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _assert_internal_access(request: Request) -> None:
    settings = get_settings()
    client_ip = extract_client_ip(request)
    token = request.headers.get("X-Internal-Token")

    if not is_valid_internal_token(
        expected_token=settings.internal_api_token,
        received_token=token,
    ):
        logger.warning("internal_promo_auth_failed", reason="invalid_token", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})

    if not is_client_ip_allowed(client_ip=client_ip, allowlist=settings.internal_api_allowlist):
        logger.warning("internal_promo_auth_failed", reason="ip_not_allowed", client_ip=client_ip)
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
        attempt_counts = await PromoRepo.count_attempts_by_result(session, since_utc=window_since_utc)
        redemption_counts = await PromoRepo.count_redemptions_by_status(session, since_utc=window_since_utc)
        discount_redemption_counts = await PromoRepo.count_discount_redemptions_by_status(
            session,
            since_utc=window_since_utc,
        )
        campaign_counts = await PromoRepo.count_campaigns_by_status(session)
        paused_recent = await PromoRepo.count_paused_campaigns_since(session, since_utc=window_since_utc)
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
