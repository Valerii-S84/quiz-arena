from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.purchases_repo import PurchasesRepo
from app.economy.purchases.catalog import canonical_product_code, get_product
from app.economy.purchases.errors import (
    ProductNotFoundError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
)
from app.economy.purchases.types import PurchaseCreditResult

from .credit_logging import credited_replay_result, log_mark_paid_finished, log_mark_paid_started
from .credit_marked import credit_marked_purchase_assets
from .events import _emit_purchase_event
from .payment_validation import (
    sanitize_successful_payment_payload,
    successful_payment_validation_error,
)
from .payment_validation_review import mark_payment_validation_failed

RECOVERABLE_PAYMENT_STATUSES = frozenset(
    {"PRECHECKOUT_OK", "INVOICE_SENT", "CREATED", "PAID_UNCREDITED"}
)


def _repair_credited_payment_evidence(
    *,
    purchase,
    invoice_payload: str,
    telegram_payment_charge_id: str,
    raw_successful_payment: dict[str, object],
) -> None:
    existing_charge_id = purchase.telegram_payment_charge_id
    if existing_charge_id is not None:
        if existing_charge_id != telegram_payment_charge_id:
            raise PurchasePrecheckoutValidationError
        return

    validation_error = successful_payment_validation_error(
        purchase=purchase,
        invoice_payload=invoice_payload,
        telegram_payment_charge_id=telegram_payment_charge_id,
        raw_successful_payment=raw_successful_payment,
    )
    if validation_error is not None:
        raise PurchasePrecheckoutValidationError

    purchase.telegram_payment_charge_id = telegram_payment_charge_id
    purchase.raw_successful_payment = sanitize_successful_payment_payload(raw_successful_payment)


async def _mark_successful_payment(
    session: AsyncSession,
    *,
    purchase,
    user_id: int,
    telegram_payment_charge_id: str,
    raw_successful_payment: dict[str, object],
    now_utc: datetime,
) -> None:
    previous_status = purchase.status
    log_mark_paid_started(
        purchase=purchase,
        user_id=user_id,
        previous_status=previous_status,
        telegram_payment_charge_id=telegram_payment_charge_id,
    )
    purchase.telegram_payment_charge_id = telegram_payment_charge_id
    purchase.raw_successful_payment = sanitize_successful_payment_payload(raw_successful_payment)
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
    log_mark_paid_finished(
        purchase=purchase,
        user_id=user_id,
        previous_status=previous_status,
        telegram_payment_charge_id=telegram_payment_charge_id,
    )


async def mark_successful_payment_paid_uncredited(
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
        _repair_credited_payment_evidence(
            purchase=purchase,
            invoice_payload=invoice_payload,
            telegram_payment_charge_id=telegram_payment_charge_id,
            raw_successful_payment=raw_successful_payment,
        )
        return credited_replay_result(purchase=purchase, user_id=user_id)

    if purchase.status not in RECOVERABLE_PAYMENT_STATUSES:
        raise PurchasePrecheckoutValidationError

    validation_error = successful_payment_validation_error(
        purchase=purchase,
        invoice_payload=invoice_payload,
        telegram_payment_charge_id=telegram_payment_charge_id,
        raw_successful_payment=raw_successful_payment,
    )
    if validation_error is not None:
        return await mark_payment_validation_failed(
            session,
            purchase=purchase,
            invoice_payload=invoice_payload,
            telegram_payment_charge_id=telegram_payment_charge_id,
            raw_successful_payment=raw_successful_payment,
            reason=validation_error,
            now_utc=now_utc,
        )

    await _mark_successful_payment(
        session,
        purchase=purchase,
        user_id=user_id,
        telegram_payment_charge_id=telegram_payment_charge_id,
        raw_successful_payment=raw_successful_payment,
        now_utc=now_utc,
    )
    return PurchaseCreditResult(
        purchase_id=purchase.id,
        product_code=canonical_product_code(purchase.product_code),
        status=purchase.status,
        idempotent_replay=False,
    )


async def credit_paid_purchase(
    session: AsyncSession,
    *,
    purchase_id: UUID,
    user_id: int,
    now_utc: datetime,
) -> PurchaseCreditResult:
    purchase = await PurchasesRepo.get_for_credit_lock(session, purchase_id)
    if purchase is None or purchase.user_id != user_id:
        raise PurchaseNotFoundError

    if purchase.status == "CREDITED":
        return credited_replay_result(purchase=purchase, user_id=user_id)

    if purchase.status != "PAID_UNCREDITED" or not purchase.telegram_payment_charge_id:
        raise PurchasePrecheckoutValidationError

    product = get_product(purchase.product_code)
    if product is None:
        raise ProductNotFoundError

    await credit_marked_purchase_assets(
        session,
        purchase=purchase,
        user_id=user_id,
        product=product,
        telegram_payment_charge_id=purchase.telegram_payment_charge_id,
        now_utc=now_utc,
    )

    return PurchaseCreditResult(
        purchase_id=purchase.id,
        product_code=product.product_code,
        status=purchase.status,
        idempotent_replay=False,
    )


async def apply_successful_payment(
    session: AsyncSession,
    *,
    user_id: int,
    invoice_payload: str,
    telegram_payment_charge_id: str,
    raw_successful_payment: dict[str, object],
    now_utc: datetime,
) -> PurchaseCreditResult:
    paid_result = await mark_successful_payment_paid_uncredited(
        session,
        user_id=user_id,
        invoice_payload=invoice_payload,
        telegram_payment_charge_id=telegram_payment_charge_id,
        raw_successful_payment=raw_successful_payment,
        now_utc=now_utc,
    )
    if paid_result.status == "FAILED_CREDIT_PENDING_REVIEW":
        raise PurchasePrecheckoutValidationError
    if paid_result.status == "CREDITED":
        return paid_result
    return await credit_paid_purchase(
        session,
        purchase_id=paid_result.purchase_id,
        user_id=user_id,
        now_utc=now_utc,
    )
