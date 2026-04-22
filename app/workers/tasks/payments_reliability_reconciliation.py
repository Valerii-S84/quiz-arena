from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog

from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.reconciliation_runs_repo import ReconciliationRunsRepo
from app.db.session import SessionLocal
from app.services.alerts import send_ops_alert
from app.services.payments_reliability import (
    compute_product_stars_mismatch_count,
    compute_reconciliation_diff,
    reconciliation_status,
)

logger = structlog.get_logger("app.workers.tasks.payments_reliability")


async def run_payments_reconciliation_async(*, stale_minutes: int = 30) -> dict[str, int | str]:
    started_at = datetime.now(timezone.utc)
    stale_cutoff = started_at - timedelta(minutes=stale_minutes)

    async with SessionLocal.begin() as session:
        paid_purchases_count = await PurchasesRepo.count_paid_purchases(session)
        credited_purchases_count = await LedgerRepo.count_distinct_purchase_credits(session)
        paid_stars_total = await PurchasesRepo.sum_paid_stars_amount(session)
        credited_stars_total = await LedgerRepo.sum_distinct_purchase_stars_for_credits(session)
        paid_stars_by_product = await PurchasesRepo.sum_paid_stars_amount_by_product(session)
        credited_stars_by_product = (
            await LedgerRepo.sum_distinct_purchase_stars_for_credits_by_product(session)
        )
        product_stars_mismatch_count = compute_product_stars_mismatch_count(
            paid_stars_by_product=paid_stars_by_product,
            credited_stars_by_product=credited_stars_by_product,
        )
        stale_paid_uncredited_count = await PurchasesRepo.count_paid_uncredited_older_than(
            session,
            older_than_utc=stale_cutoff,
        )
        diff_count = compute_reconciliation_diff(
            paid_purchases_count=paid_purchases_count,
            credited_purchases_count=credited_purchases_count,
            stale_paid_uncredited_count=stale_paid_uncredited_count,
            paid_stars_total=paid_stars_total,
            credited_stars_total=credited_stars_total,
            product_stars_mismatch_count=product_stars_mismatch_count,
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
        "paid_stars_total": paid_stars_total,
        "credited_stars_total": credited_stars_total,
        "product_stars_mismatch_count": product_stars_mismatch_count,
        "diff_count": diff_count,
        "status": status,
    }
    if diff_count > 0:
        payload: dict[str, object] = {key: value for key, value in result.items()}
        await send_ops_alert(
            event="payments_reconciliation_diff_detected",
            payload=payload,
        )
        logger.warning("payments_reconciliation_diff_detected", **result)
    else:
        logger.info("payments_reconciliation_finished", **result)
    return result
