from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
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


@router.post("/internal/promo/redeem", response_model=PromoRedeemResponse)
async def redeem_promo(payload: PromoRedeemRequest, request: Request) -> PromoRedeemResponse:
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
