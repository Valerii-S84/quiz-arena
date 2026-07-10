from __future__ import annotations

import hashlib

import structlog

from app.economy.purchases.catalog import canonical_product_code
from app.economy.purchases.types import PurchaseCreditResult

logger = structlog.get_logger(__name__)


def payment_identifier_hash(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _payment_log_payload(
    *,
    purchase,
    user_id: int,
    product_code: str | None = None,
    telegram_payment_charge_id: str | None = None,
) -> dict[str, object]:
    charge_id = telegram_payment_charge_id or purchase.telegram_payment_charge_id
    return {
        "purchase_id": str(purchase.id),
        "user_id": user_id,
        "product_code": product_code or purchase.product_code,
        "status": purchase.status,
        "stars_amount": purchase.stars_amount,
        "telegram_payment_charge_id_hash": payment_identifier_hash(charge_id),
    }


def log_mark_paid_started(
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


def log_mark_paid_finished(
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


def log_credit_started(*, purchase, user_id: int, product_code: str) -> None:
    logger.info(
        "payment_credit_started",
        **_payment_log_payload(purchase=purchase, user_id=user_id, product_code=product_code),
    )


def log_credit_finished(
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


def log_credit_failed(
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


def credited_replay_result(*, purchase, user_id: int) -> PurchaseCreditResult:
    log_credit_finished(
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
