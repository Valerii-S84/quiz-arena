from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.purchases_repo import PurchasesRepo
from app.economy.purchases.catalog import canonical_product_code, get_product
from app.economy.purchases.errors import (
    ProductNotFoundError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
)
from app.economy.purchases.types import PurchaseCreditResult

from .credit_assets import credit_purchase_assets
from .events import _emit_purchase_event

logger = structlog.get_logger(__name__)
RECOVERABLE_PAYMENT_STATUSES = frozenset(
    {"PRECHECKOUT_OK", "INVOICE_SENT", "CREATED", "PAID_UNCREDITED"}
)


def _payment_log_payload(
    *,
    purchase,
    user_id: int,
    product_code: str | None = None,
    telegram_payment_charge_id: str | None = None,
) -> dict[str, object]:
    return {
        "purchase_id": str(purchase.id),
        "user_id": user_id,
        "product_code": product_code or purchase.product_code,
        "status": purchase.status,
        "stars_amount": purchase.stars_amount,
        "telegram_payment_charge_id": telegram_payment_charge_id
        or purchase.telegram_payment_charge_id,
    }


def _log_mark_paid_started(
    *,
    purchase,
    user_id: int,
    previous_status: str,
    telegram_payment_charge_id: str,
) -> None:
    logger.info(
        "payment_successful_mark_paid_started",
        **_payment_log_payload(
            purchase=purchase,
            user_id=user_id,
            telegram_payment_charge_id=telegram_payment_charge_id,
        ),
        previous_status=previous_status,
    )


def _log_mark_paid_finished(
    *,
    purchase,
    user_id: int,
    previous_status: str,
    telegram_payment_charge_id: str,
) -> None:
    logger.info(
        "payment_successful_mark_paid_finished",
        **_payment_log_payload(
            purchase=purchase,
            user_id=user_id,
            telegram_payment_charge_id=telegram_payment_charge_id,
        ),
        previous_status=previous_status,
    )


def _log_credit_started(*, purchase, user_id: int, product_code: str) -> None:
    logger.info(
        "payment_credit_started",
        **_payment_log_payload(purchase=purchase, user_id=user_id, product_code=product_code),
    )


def _log_credit_finished(
    *,
    purchase,
    user_id: int,
    product_code: str,
    telegram_payment_charge_id: str | None,
    idempotent_replay: bool = False,
) -> None:
    logger.info(
        "payment_credit_finished",
        **_payment_log_payload(
            purchase=purchase,
            user_id=user_id,
            product_code=product_code,
            telegram_payment_charge_id=telegram_payment_charge_id,
        ),
        idempotent_replay=idempotent_replay,
    )


def _log_credit_failed(
    *,
    purchase,
    user_id: int,
    product_code: str,
    error_type: str,
) -> None:
    logger.warning(
        "payment_credit_failed",
        **_payment_log_payload(purchase=purchase, user_id=user_id, product_code=product_code),
        error_type=error_type,
    )


def _credited_replay_result(*, purchase, user_id: int) -> PurchaseCreditResult:
    _log_credit_finished(
        purchase=purchase,
        user_id=user_id,
        product_code=purchase.product_code,
        telegram_payment_charge_id=purchase.telegram_payment_charge_id,
        idempotent_replay=True,
    )
    return PurchaseCreditResult(
        purchase_id=purchase.id,
        product_code=canonical_product_code(purchase.product_code),
        status=purchase.status,
        idempotent_replay=True,
    )


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
    _log_mark_paid_started(
        purchase=purchase,
        user_id=user_id,
        previous_status=previous_status,
        telegram_payment_charge_id=telegram_payment_charge_id,
    )
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
    _log_mark_paid_finished(
        purchase=purchase,
        user_id=user_id,
        previous_status=previous_status,
        telegram_payment_charge_id=telegram_payment_charge_id,
    )


async def _credit_marked_purchase(
    session: AsyncSession,
    *,
    purchase,
    user_id: int,
    product,
    telegram_payment_charge_id: str,
    now_utc: datetime,
) -> None:
    _log_credit_started(purchase=purchase, user_id=user_id, product_code=product.product_code)
    try:
        await credit_purchase_assets(
            session,
            user_id=user_id,
            purchase=purchase,
            product=product,
            now_utc=now_utc,
        )
    except Exception as exc:
        # Re-raise to preserve rollback behavior while making failed credit attempts visible.
        _log_credit_failed(
            purchase=purchase,
            user_id=user_id,
            product_code=product.product_code,
            error_type=type(exc).__name__,
        )
        raise
    _log_credit_finished(
        purchase=purchase,
        user_id=user_id,
        product_code=product.product_code,
        telegram_payment_charge_id=telegram_payment_charge_id,
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
    purchase = await PurchasesRepo.get_by_invoice_payload_for_update(session, invoice_payload)
    if purchase is None or purchase.user_id != user_id:
        raise PurchaseNotFoundError

    if purchase.status == "CREDITED":
        return _credited_replay_result(purchase=purchase, user_id=user_id)

    if purchase.status not in RECOVERABLE_PAYMENT_STATUSES:
        raise PurchasePrecheckoutValidationError

    _validate_successful_payment_payload(
        purchase=purchase,
        raw_successful_payment=raw_successful_payment,
    )

    await _mark_successful_payment(
        session,
        purchase=purchase,
        user_id=user_id,
        telegram_payment_charge_id=telegram_payment_charge_id,
        raw_successful_payment=raw_successful_payment,
        now_utc=now_utc,
    )

    product = get_product(purchase.product_code)
    if product is None:
        raise ProductNotFoundError

    await _credit_marked_purchase(
        session,
        purchase=purchase,
        user_id=user_id,
        product=product,
        telegram_payment_charge_id=telegram_payment_charge_id,
        now_utc=now_utc,
    )

    return PurchaseCreditResult(
        purchase_id=purchase.id,
        product_code=product.product_code,
        status=purchase.status,
        idempotent_replay=False,
    )


def _validate_successful_payment_payload(
    *,
    purchase,
    raw_successful_payment: dict[str, object],
) -> None:
    if purchase.stars_amount == 0:
        return

    currency = raw_successful_payment.get("currency")
    if currency != "XTR":
        raise PurchasePrecheckoutValidationError

    total_amount = raw_successful_payment.get("total_amount")
    if total_amount is None:
        return
    if not isinstance(total_amount, int) or total_amount != purchase.stars_amount:
        raise PurchasePrecheckoutValidationError


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
            product_code=canonical_product_code(purchase.product_code),
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
        product_code=product.product_code,
        status=purchase.status,
        idempotent_replay=False,
    )
