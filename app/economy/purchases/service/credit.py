from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.purchases_repo import PurchasesRepo
from app.economy.purchases.catalog import get_product
from app.economy.purchases.errors import (
    ProductNotFoundError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
)
from app.economy.purchases.types import PurchaseCreditResult

from .credit_assets import credit_purchase_assets
from .events import _emit_purchase_event


async def apply_successful_payment(
    session: AsyncSession,
    *,
    user_id: int,
    invoice_payload: str,
    telegram_payment_charge_id: str,
    raw_successful_payment: dict[str, object],
    now_utc: datetime,
) -> PurchaseCreditResult:
    purchase = await PurchasesRepo.get_by_invoice_payload_for_update(session, invoice_payload)
    if purchase is None or purchase.user_id != user_id:
        raise PurchaseNotFoundError

    if purchase.status == "CREDITED":
        return PurchaseCreditResult(
            purchase_id=purchase.id,
            product_code=purchase.product_code,
            status=purchase.status,
            idempotent_replay=True,
        )

    if purchase.status not in {
        "PRECHECKOUT_OK",
        "INVOICE_SENT",
        "CREATED",
        "PAID_UNCREDITED",
    }:
        raise PurchasePrecheckoutValidationError

    previous_status = purchase.status
    purchase.telegram_payment_charge_id = telegram_payment_charge_id
    purchase.raw_successful_payment = raw_successful_payment
    purchase.status = "PAID_UNCREDITED"
    if purchase.paid_at is None or previous_status != "PAID_UNCREDITED":
        purchase.paid_at = now_utc
    if previous_status != "PAID_UNCREDITED":
        await _emit_purchase_event(
            session,
            event_type="purchase_paid_uncredited",
            purchase=purchase,
            happened_at=now_utc,
            extra_payload={"previous_status": previous_status},
        )

    product = get_product(purchase.product_code)
    if product is None:
        raise ProductNotFoundError

    await credit_purchase_assets(
        session,
        user_id=user_id,
        purchase=purchase,
        product=product,
        now_utc=now_utc,
    )

    return PurchaseCreditResult(
        purchase_id=purchase.id,
        product_code=purchase.product_code,
        status=purchase.status,
        idempotent_replay=False,
    )


async def apply_zero_cost_purchase(
    session: AsyncSession,
    *,
    purchase_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> PurchaseCreditResult:
    purchase = await PurchasesRepo.get_by_id_for_update(session, purchase_id)
    if purchase is None or purchase.user_id != user_id:
        raise PurchaseNotFoundError
    if purchase.status == "CREDITED":
        return PurchaseCreditResult(
            purchase_id=purchase.id,
            product_code=purchase.product_code,
            status=purchase.status,
            idempotent_replay=True,
        )
    if purchase.stars_amount != 0:
        raise PurchasePrecheckoutValidationError
    if purchase.status not in {"CREATED", "INVOICE_SENT", "PRECHECKOUT_OK", "PAID_UNCREDITED"}:
        raise PurchasePrecheckoutValidationError

    previous_status = purchase.status
    purchase.status = "PAID_UNCREDITED"
    if purchase.paid_at is None:
        purchase.paid_at = now_utc
    await _emit_purchase_event(
        session,
        event_type="purchase_paid_uncredited",
        purchase=purchase,
        happened_at=now_utc,
        extra_payload={"previous_status": previous_status, "zero_cost": True},
    )

    product = get_product(purchase.product_code)
    if product is None:
        raise ProductNotFoundError
    await credit_purchase_assets(
        session,
        user_id=user_id,
        purchase=purchase,
        product=product,
        now_utc=now_utc,
    )
    return PurchaseCreditResult(
        purchase_id=purchase.id,
        product_code=purchase.product_code,
        status=purchase.status,
        idempotent_replay=False,
    )
