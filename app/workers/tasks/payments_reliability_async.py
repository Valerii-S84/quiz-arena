from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog

from app.db.repo.promo_repo import PromoRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.session import SessionLocal
from app.economy.purchases.errors import (
    ProductNotFoundError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
)
from app.economy.purchases.recovery import MAX_CREDIT_RECOVERY_ATTEMPTS, increment_recovery_failures
from app.economy.purchases.service import PurchaseService
from app.services.alerts import send_ops_alert
from app.workers.tasks.payments_reliability_reconciliation import (
    run_payments_reconciliation_async as run_payments_reconciliation_async,
)

logger = structlog.get_logger("app.workers.tasks.payments_reliability")

__all__ = [
    "expire_stale_unpaid_invoices_async",
    "recover_paid_uncredited_async",
    "run_payments_reconciliation_async",
    "run_refund_promo_rollback_async",
]


async def expire_stale_unpaid_invoices_async(*, stale_minutes: int = 30) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    stale_cutoff = now_utc - timedelta(minutes=stale_minutes)

    async with SessionLocal.begin() as session:
        expired_invoices = await PurchasesRepo.expire_stale_unpaid_invoices(
            session,
            older_than_utc=stale_cutoff,
        )

    result = {"expired_invoices": expired_invoices}
    logger.info("stale_unpaid_invoices_expiry_finished", **result)
    return result


async def run_refund_promo_rollback_async(*, batch_size: int = 100) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        purchase_ids = await PromoRepo.get_refunded_purchase_ids_with_pending_redemption_revoke(
            session,
            limit=batch_size,
        )

    summary: dict[str, int] = {
        "examined": len(purchase_ids),
        "rolled_back": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 0,
    }

    for purchase_id in purchase_ids:
        try:
            async with SessionLocal.begin() as session:
                purchase = await PurchasesRepo.get_by_id_for_update(session, purchase_id)
                if purchase is None:
                    summary["missing"] += 1
                    continue
                if purchase.status != "REFUNDED" or purchase.applied_promo_code_id is None:
                    summary["skipped"] += 1
                    continue

                _, _, rollback_applied = await PromoRepo.revoke_redemption_for_refund(
                    session,
                    purchase_id=purchase.id,
                    promo_code_id=purchase.applied_promo_code_id,
                    now_utc=now_utc,
                )
                if rollback_applied:
                    summary["rolled_back"] += 1
                else:
                    summary["skipped"] += 1
        except Exception:
            summary["errors"] += 1
            logger.exception("promo_refund_rollback_error", purchase_id=str(purchase_id))

    logger.info("promo_refund_rollback_finished", **summary)
    return summary


async def _recover_single_purchase(purchase_id: UUID, *, now_utc: datetime) -> str:
    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_for_credit_lock(session, purchase_id)
        if purchase is None:
            return "missing"
        if purchase.status != "PAID_UNCREDITED":
            return "skipped"

        if purchase.telegram_payment_charge_id is None:
            purchase.status = "FAILED_CREDIT_PENDING_REVIEW"
            return "review"
        if not isinstance(purchase.raw_successful_payment, dict):
            purchase.status = "FAILED_CREDIT_PENDING_REVIEW"
            return "review"

        try:
            await PurchaseService.apply_successful_payment(
                session,
                user_id=purchase.user_id,
                invoice_payload=purchase.invoice_payload,
                telegram_payment_charge_id=purchase.telegram_payment_charge_id,
                raw_successful_payment=purchase.raw_successful_payment,
                now_utc=now_utc,
            )
        except (
            ProductNotFoundError,
            PurchaseNotFoundError,
            PurchasePrecheckoutValidationError,
        ):
            payload, failures = increment_recovery_failures(purchase.raw_successful_payment)
            purchase.raw_successful_payment = payload

            if failures >= MAX_CREDIT_RECOVERY_ATTEMPTS:
                purchase.status = "FAILED_CREDIT_PENDING_REVIEW"
                return "review"

            return "retryable_failure"

    return "credited"


async def recover_paid_uncredited_async(
    *, batch_size: int = 100, stale_minutes: int = 2
) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    stale_cutoff = now_utc - timedelta(minutes=stale_minutes)

    async with SessionLocal.begin() as session:
        candidates = await PurchasesRepo.get_paid_uncredited_older_than(
            session,
            older_than_utc=stale_cutoff,
            limit=batch_size,
        )

    summary: dict[str, int] = {
        "examined": len(candidates),
        "credited": 0,
        "review": 0,
        "retryable_failure": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 0,
    }

    for purchase in candidates:
        try:
            outcome = await _recover_single_purchase(purchase.id, now_utc=now_utc)
        except Exception:
            summary["errors"] += 1
            logger.exception("paid_uncredited_recovery_error", purchase_id=str(purchase.id))
            continue

        summary[outcome] = summary.get(outcome, 0) + 1

    if summary["review"] > 0 or summary["errors"] > 0:
        payload: dict[str, object] = {key: value for key, value in summary.items()}
        await send_ops_alert(
            event="payments_recovery_review_required",
            payload=payload,
        )

    logger.info("paid_uncredited_recovery_finished", **summary)
    return summary
