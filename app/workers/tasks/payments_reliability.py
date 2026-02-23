from __future__ import annotations

from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.payments_reliability_async import (
    expire_stale_unpaid_invoices_async as _expire_stale_unpaid_invoices_async,
)
from app.workers.tasks.payments_reliability_async import (
    recover_paid_uncredited_async as _recover_paid_uncredited_async,
)
from app.workers.tasks.payments_reliability_async import (
    run_payments_reconciliation_async as _run_payments_reconciliation_async,
)
from app.workers.tasks.payments_reliability_async import (
    run_refund_promo_rollback_async as _run_refund_promo_rollback_async,
)
from app.workers.tasks.payments_reliability_schedule import configure_payments_reliability_schedule

expire_stale_unpaid_invoices_async = _expire_stale_unpaid_invoices_async
recover_paid_uncredited_async = _recover_paid_uncredited_async
run_refund_promo_rollback_async = _run_refund_promo_rollback_async
run_payments_reconciliation_async = _run_payments_reconciliation_async

__all__ = [
    "expire_stale_unpaid_invoices",
    "expire_stale_unpaid_invoices_async",
    "recover_paid_uncredited",
    "recover_paid_uncredited_async",
    "run_payments_reconciliation",
    "run_payments_reconciliation_async",
    "run_refund_promo_rollback",
    "run_refund_promo_rollback_async",
]


@celery_app.task(name="app.workers.tasks.payments_reliability.recover_paid_uncredited")
def recover_paid_uncredited(batch_size: int = 100, stale_minutes: int = 2) -> dict[str, int]:
    return run_async_job(
        recover_paid_uncredited_async(
            batch_size=batch_size,
            stale_minutes=stale_minutes,
        )
    )


@celery_app.task(name="app.workers.tasks.payments_reliability.expire_stale_unpaid_invoices")
def expire_stale_unpaid_invoices(stale_minutes: int = 30) -> dict[str, int]:
    return run_async_job(expire_stale_unpaid_invoices_async(stale_minutes=stale_minutes))


@celery_app.task(name="app.workers.tasks.payments_reliability.run_refund_promo_rollback")
def run_refund_promo_rollback(batch_size: int = 100) -> dict[str, int]:
    return run_async_job(run_refund_promo_rollback_async(batch_size=batch_size))


@celery_app.task(name="app.workers.tasks.payments_reliability.run_payments_reconciliation")
def run_payments_reconciliation(stale_minutes: int = 30) -> dict[str, int | str]:
    return run_async_job(run_payments_reconciliation_async(stale_minutes=stale_minutes))


configure_payments_reliability_schedule(celery_app)
