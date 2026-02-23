from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Request

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

from .internal_promo_helpers import _as_response, _assert_internal_access
from .internal_promo_models import PromoRedeemRequest, PromoRedeemResponse


async def redeem_promo(
    *,
    payload: PromoRedeemRequest,
    request: Request,
) -> PromoRedeemResponse:
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
