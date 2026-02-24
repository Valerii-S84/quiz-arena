from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, Request

from app.db.repo.promo_repo import PromoRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.session import SessionLocal
from app.economy.purchases.errors import (
    PurchaseNotFoundError,
    PurchaseRefundInvariantError,
    PurchaseRefundValidationError,
)
from app.economy.purchases.service import PurchaseService

from .internal_promo_helpers import _assert_internal_access
from .internal_promo_models import PromoRefundRollbackRequest, PromoRefundRollbackResponse

logger = structlog.get_logger(__name__)


async def rollback_promo_for_refund(
    *,
    payload: PromoRefundRollbackRequest,
    request: Request,
) -> PromoRefundRollbackResponse:
    _assert_internal_access(request)
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        try:
            refund_result = await PurchaseService.refund_purchase(
                session,
                purchase_id=payload.purchase_id,
                now_utc=now_utc,
            )
        except PurchaseNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "E_PURCHASE_NOT_FOUND"}) from exc
        except PurchaseRefundValidationError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "E_PURCHASE_REFUND_NOT_ALLOWED"},
            ) from exc
        except PurchaseRefundInvariantError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "E_PURCHASE_REFUND_INVARIANT"},
            ) from exc

        purchase = await PurchasesRepo.get_by_id_for_update(session, payload.purchase_id)
        if purchase is None:
            raise HTTPException(status_code=404, detail={"code": "E_PURCHASE_NOT_FOUND"})

        redemption = None
        promo_code = None
        rollback_applied = False

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
            idempotent_replay=refund_result.idempotent_replay and not rollback_applied,
        )
