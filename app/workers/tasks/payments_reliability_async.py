from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog

from app.core.config import get_settings
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
    "run_telegram_stars_reconciliation_async",
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
            outcome: str | None = None
            async with SessionLocal.begin() as session:
                purchase = await PurchasesRepo.get_by_id_for_update(session, purchase_id)
                if purchase is None:
                    outcome = "missing"
                elif purchase.status != "REFUNDED" or purchase.applied_promo_code_id is None:
                    outcome = "skipped"
                else:
                    _, _, rollback_applied = await PromoRepo.revoke_redemption_for_refund(
                        session,
                        purchase_id=purchase.id,
                        promo_code_id=purchase.applied_promo_code_id,
                        now_utc=now_utc,
                    )
                    outcome = "rolled_back" if rollback_applied else "skipped"
            if outcome is not None:
                summary[outcome] += 1
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
    logger.info(
        "payment_recovery_started",
        batch_size=batch_size,
        stale_minutes=stale_minutes,
    )

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
        except Exception as exc:
            summary["errors"] += 1
            logger.warning(
                "payment_recovery_failed",
                purchase_id=str(purchase.id),
                outcome="error",
                error_type=type(exc).__name__,
            )
            logger.exception("paid_uncredited_recovery_error", purchase_id=str(purchase.id))
            continue

        summary[outcome] = summary.get(outcome, 0) + 1
        if outcome in {"review", "retryable_failure"}:
            logger.warning(
                "payment_recovery_failed",
                purchase_id=str(purchase.id),
                outcome=outcome,
            )

    if summary["review"] > 0 or summary["errors"] > 0:
        payload: dict[str, object] = {key: value for key, value in summary.items()}
        await send_ops_alert(
            event="payments_recovery_review_required",
            payload=payload,
        )

    logger.info("payment_recovery_finished", **summary)
    logger.info("paid_uncredited_recovery_finished", **summary)
    return summary


async def run_payment_invariant_alerts_async(
    *,
    precheckout_stale_minutes: int = 3,
    paid_uncredited_stale_seconds: int = 60,
) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    precheckout_cutoff = now_utc - timedelta(minutes=precheckout_stale_minutes)
    paid_uncredited_cutoff = now_utc - timedelta(seconds=paid_uncredited_stale_seconds)

    async with SessionLocal.begin() as session:
        precheckout_stuck = await PurchasesRepo.count_precheckout_ok_older_than(
            session,
            older_than_utc=precheckout_cutoff,
        )
        paid_uncredited_stuck = await PurchasesRepo.count_paid_uncredited_older_than(
            session,
            older_than_utc=paid_uncredited_cutoff,
        )
        credited_premium_missing_entitlement = (
            await PurchasesRepo.count_credited_premium_without_entitlement(session)
        )
        credited_stars_missing_purchase_credit = (
            await PurchasesRepo.count_credited_stars_without_purchase_credit(session)
        )

    summary = {
        "precheckout_stuck": precheckout_stuck,
        "paid_uncredited_stuck": paid_uncredited_stuck,
        "credited_premium_missing_entitlement": credited_premium_missing_entitlement,
        "credited_stars_missing_purchase_credit": credited_stars_missing_purchase_credit,
    }
    await _send_payment_invariant_alerts(summary)
    logger.info("payment_invariant_alerts_finished", **summary)
    return summary


async def _send_payment_invariant_alerts(summary: dict[str, int]) -> None:
    if summary["precheckout_stuck"] > 0:
        await send_ops_alert(
            event="payments_precheckout_stuck_detected",
            payload={"precheckout_stuck": summary["precheckout_stuck"]},
        )
    if summary["paid_uncredited_stuck"] > 0:
        await send_ops_alert(
            event="payments_paid_uncredited_stuck_detected",
            payload={"paid_uncredited_stuck": summary["paid_uncredited_stuck"]},
        )
    credit_invariant_failures = (
        summary["credited_premium_missing_entitlement"]
        + summary["credited_stars_missing_purchase_credit"]
    )
    if credit_invariant_failures > 0:
        await send_ops_alert(
            event="payments_credit_invariant_failed",
            payload={
                "credit_invariant_failures": credit_invariant_failures,
                "credited_premium_missing_entitlement": summary[
                    "credited_premium_missing_entitlement"
                ],
                "credited_stars_missing_purchase_credit": summary[
                    "credited_stars_missing_purchase_credit"
                ],
            },
        )


async def run_telegram_stars_reconciliation_async() -> dict[str, object]:
    settings = get_settings()
    enabled = bool(getattr(settings, "telegram_stars_reconciliation_enabled", False))
    dry_run = bool(getattr(settings, "telegram_stars_reconciliation_dry_run", True))
    auto_recovery_enabled = bool(getattr(settings, "telegram_stars_auto_recovery_enabled", False))
    if not enabled:
        result: dict[str, object] = {
            "status": "disabled",
            "dry_run": dry_run,
            "auto_recovery_enabled": auto_recovery_enabled,
            "transactions_examined": 0,
        }
        logger.info("telegram_stars_reconciliation_skipped", **result)
        return result

    result = {
        "status": "dry_run_not_started",
        "dry_run": dry_run,
        "auto_recovery_enabled": auto_recovery_enabled,
        "transactions_examined": 0,
    }
    logger.info("telegram_stars_reconciliation_dry_run_pending", **result)
    return result
