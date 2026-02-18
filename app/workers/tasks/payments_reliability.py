from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from celery.schedules import crontab

from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.reconciliation_runs_repo import ReconciliationRunsRepo
from app.db.session import SessionLocal
from app.economy.purchases.errors import (
    ProductNotFoundError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
)
from app.economy.purchases.recovery import MAX_CREDIT_RECOVERY_ATTEMPTS, increment_recovery_failures
from app.economy.purchases.service import PurchaseService
from app.services.payments_reliability import compute_reconciliation_diff, reconciliation_status
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


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
        except (ProductNotFoundError, PurchaseNotFoundError, PurchasePrecheckoutValidationError):
            payload, failures = increment_recovery_failures(purchase.raw_successful_payment)
            purchase.raw_successful_payment = payload

            if failures >= MAX_CREDIT_RECOVERY_ATTEMPTS:
                purchase.status = "FAILED_CREDIT_PENDING_REVIEW"
                return "review"

            return "retryable_failure"

    return "credited"


async def recover_paid_uncredited_async(*, batch_size: int = 100, stale_minutes: int = 2) -> dict[str, int]:
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

    logger.info("paid_uncredited_recovery_finished", **summary)
    return summary


async def run_payments_reconciliation_async(*, stale_minutes: int = 30) -> dict[str, int | str]:
    started_at = datetime.now(timezone.utc)
    stale_cutoff = started_at - timedelta(minutes=stale_minutes)

    async with SessionLocal.begin() as session:
        paid_purchases_count = await PurchasesRepo.count_paid_purchases(session)
        credited_purchases_count = await LedgerRepo.count_distinct_purchase_credits(session)
        stale_paid_uncredited_count = await PurchasesRepo.count_paid_uncredited_older_than(
            session,
            older_than_utc=stale_cutoff,
        )
        diff_count = compute_reconciliation_diff(
            paid_purchases_count=paid_purchases_count,
            credited_purchases_count=credited_purchases_count,
            stale_paid_uncredited_count=stale_paid_uncredited_count,
        )
        status = reconciliation_status(diff_count)

        await ReconciliationRunsRepo.create(
            session,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status=status,
            diff_count=diff_count,
        )

    result: dict[str, int | str] = {
        "paid_purchases_count": paid_purchases_count,
        "credited_purchases_count": credited_purchases_count,
        "stale_paid_uncredited_count": stale_paid_uncredited_count,
        "diff_count": diff_count,
        "status": status,
    }
    logger.info("payments_reconciliation_finished", **result)
    return result


@celery_app.task(name="app.workers.tasks.payments_reliability.recover_paid_uncredited")
def recover_paid_uncredited(batch_size: int = 100, stale_minutes: int = 2) -> dict[str, int]:
    return asyncio.run(
        recover_paid_uncredited_async(
            batch_size=batch_size,
            stale_minutes=stale_minutes,
        )
    )


@celery_app.task(name="app.workers.tasks.payments_reliability.run_payments_reconciliation")
def run_payments_reconciliation(stale_minutes: int = 30) -> dict[str, int | str]:
    return asyncio.run(run_payments_reconciliation_async(stale_minutes=stale_minutes))


celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
celery_app.conf.beat_schedule.update(
    {
        "recover-paid-uncredited-every-5-minutes": {
            "task": "app.workers.tasks.payments_reliability.recover_paid_uncredited",
            "schedule": 300.0,
            "options": {"queue": "q_high"},
        },
        "payments-reconciliation-every-15-minutes": {
            "task": "app.workers.tasks.payments_reliability.run_payments_reconciliation",
            "schedule": 900.0,
            "options": {"queue": "q_normal"},
        },
        "payments-reconciliation-daily-0330-berlin": {
            "task": "app.workers.tasks.payments_reliability.run_payments_reconciliation",
            "schedule": crontab(hour=3, minute=30),
            "options": {"queue": "q_normal"},
        },
    }
)
