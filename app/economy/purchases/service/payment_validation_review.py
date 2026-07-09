from __future__ import annotations

from app.db.repo.payment_inbox_repo import PaymentReconciliationReviewsRepo
from app.economy.purchases.catalog import canonical_product_code
from app.economy.purchases.types import PurchaseCreditResult

from .credit_logging import payment_identifier_hash
from .events import _emit_purchase_event
from .payment_validation import sanitize_successful_payment_payload


async def record_successful_payment_validation_review(
    session,
    *,
    purchase,
    reason: str,
    telegram_payment_charge_id: str | None,
    sanitized_successful_payment: dict[str, object],
) -> None:
    charge_id_hash = payment_identifier_hash(telegram_payment_charge_id)
    invoice_payload_hash = payment_identifier_hash(purchase.invoice_payload)
    await PaymentReconciliationReviewsRepo.create_once(
        session,
        unique_key=f"successful_payment_validation:{purchase.id}:{reason}",
        review_type="SUCCESSFUL_PAYMENT_VALIDATION_FAILED",
        severity="HIGH",
        reason=reason,
        purchase_id=purchase.id,
        transaction_id_hash=charge_id_hash,
        safe_payload={
            "schema_version": 1,
            "source": "purchase_credit_validation",
            "purchase_id": str(purchase.id),
            "invoice_payload_hash": invoice_payload_hash,
            "telegram_payment_charge_id_hash": charge_id_hash,
            "expected_currency": getattr(purchase, "currency", None),
            "expected_total_amount": purchase.stars_amount,
            "observed_currency": sanitized_successful_payment.get("currency"),
            "observed_total_amount": sanitized_successful_payment.get("total_amount"),
            "reason": reason,
            "raw_payload_stored": False,
        },
    )


async def mark_payment_validation_failed(
    session,
    *,
    purchase,
    invoice_payload: str,
    telegram_payment_charge_id: str | None,
    raw_successful_payment: dict[str, object],
    reason: str,
    now_utc,
) -> PurchaseCreditResult:
    sanitized = sanitize_successful_payment_payload(raw_successful_payment)
    sanitized["validation_error"] = reason
    purchase.telegram_payment_charge_id = telegram_payment_charge_id
    purchase.raw_successful_payment = sanitized
    purchase.status = "FAILED_CREDIT_PENDING_REVIEW"
    purchase.paid_at = purchase.paid_at or now_utc
    await _emit_purchase_event(
        session,
        event_type="purchase_payment_validation_failed",
        purchase=purchase,
        happened_at=now_utc,
        extra_payload={
            "reason": reason,
            "invoice_payload_hash": payment_identifier_hash(invoice_payload),
        },
    )
    await record_successful_payment_validation_review(
        session,
        purchase=purchase,
        reason=reason,
        telegram_payment_charge_id=telegram_payment_charge_id,
        sanitized_successful_payment=sanitized,
    )
    return PurchaseCreditResult(
        purchase_id=purchase.id,
        product_code=canonical_product_code(purchase.product_code),
        status=purchase.status,
        idempotent_replay=False,
    )
