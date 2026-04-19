from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.reconciliation_runs_repo import ReconciliationRunsRepo
from app.db.session import SessionLocal
from app.services.payments_reliability import (
    compute_product_stars_mismatch_count,
    compute_reconciliation_diff,
    reconciliation_status,
)


async def _collect_reconciliation_metrics(
    session,
    *,
    stale_cutoff: datetime,
) -> tuple[int, int, int, int, int, int, int, str]:
    paid_purchases_count = await PurchasesRepo.count_paid_purchases(session)
    credited_purchases_count = await LedgerRepo.count_distinct_purchase_credits(session)
    paid_stars_total = await PurchasesRepo.sum_paid_stars_amount(session)
    credited_stars_total = await LedgerRepo.sum_distinct_purchase_stars_for_credits(session)
    paid_stars_by_product = await PurchasesRepo.sum_paid_stars_amount_by_product(session)
    credited_stars_by_product = await LedgerRepo.sum_distinct_purchase_stars_for_credits_by_product(
        session
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
    return (
        paid_purchases_count,
        credited_purchases_count,
        stale_paid_uncredited_count,
        paid_stars_total,
        credited_stars_total,
        product_stars_mismatch_count,
        diff_count,
        status,
    )


async def compute_payments_reconciliation_result(
    *,
    started_at: datetime,
    stale_minutes: int,
) -> dict[str, int | str]:
    stale_cutoff = started_at - timedelta(minutes=stale_minutes)

    async with SessionLocal.begin() as session:
        (
            paid_purchases_count,
            credited_purchases_count,
            stale_paid_uncredited_count,
            paid_stars_total,
            credited_stars_total,
            product_stars_mismatch_count,
            diff_count,
            status,
        ) = await _collect_reconciliation_metrics(
            session,
            stale_cutoff=stale_cutoff,
        )
        await ReconciliationRunsRepo.create(
            session,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status=status,
            diff_count=diff_count,
        )

    return {
        "paid_purchases_count": paid_purchases_count,
        "credited_purchases_count": credited_purchases_count,
        "stale_paid_uncredited_count": stale_paid_uncredited_count,
        "paid_stars_total": paid_stars_total,
        "credited_stars_total": credited_stars_total,
        "product_stars_mismatch_count": product_stars_mismatch_count,
        "diff_count": diff_count,
        "status": status,
    }
