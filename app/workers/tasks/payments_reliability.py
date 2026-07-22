from __future__ import annotations

from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.task_heartbeat import run_tracked_async_job
from app.workers.tasks.payments_reliability_async import (
    expire_stale_unpaid_invoices_async as _expire_stale_unpaid_invoices_async,
)
from app.workers.tasks.payments_reliability_async import (
    recover_paid_uncredited_async as _recover_paid_uncredited_async,
)
from app.workers.tasks.payments_reliability_async import (
    run_payment_invariant_alerts_async as _run_payment_invariant_alerts_async,
)
from app.workers.tasks.payments_reliability_async import (
    run_payments_reconciliation_async as _run_payments_reconciliation_async,
)
from app.workers.tasks.payments_reliability_async import (
    run_refund_promo_rollback_async as _run_refund_promo_rollback_async,
)
from app.workers.tasks.payments_reliability_async import (
    run_telegram_stars_reconciliation_async as _run_telegram_stars_reconciliation_async,
)
from app.workers.tasks.payments_reliability_schedule import configure_payments_reliability_schedule

expire_stale_unpaid_invoices_async = _expire_stale_unpaid_invoices_async
recover_paid_uncredited_async = _recover_paid_uncredited_async
run_payment_invariant_alerts_async = _run_payment_invariant_alerts_async
run_refund_promo_rollback_async = _run_refund_promo_rollback_async
run_payments_reconciliation_async = _run_payments_reconciliation_async
run_telegram_stars_reconciliation_async = _run_telegram_stars_reconciliation_async

__all__ = [
    "expire_stale_unpaid_invoices",
    "expire_stale_unpaid_invoices_async",
    "recover_paid_uncredited",
    "recover_paid_uncredited_async",
    "run_payment_invariant_alerts",
    "run_payment_invariant_alerts_async",
    "run_payments_reconciliation",
    "run_payments_reconciliation_async",
    "run_refund_promo_rollback",
    "run_refund_promo_rollback_async",
    "run_telegram_stars_reconciliation",
    "run_telegram_stars_reconciliation_async",
]


@celery_app.task(name="app.workers.tasks.payments_reliability.recover_paid_uncredited")
def recover_paid_uncredited(batch_size: int = 100, stale_minutes: int = 2) -> dict[str, int]:
    return run_tracked_async_job(
        task_name="app.workers.tasks.payments_reliability.recover_paid_uncredited",
        schedule_key="recover-paid-uncredited-every-5-minutes",
        awaitable=recover_paid_uncredited_async(
            batch_size=batch_size,
            stale_minutes=stale_minutes,
        ),
    )


@celery_app.task(name="app.workers.tasks.payments_reliability.run_payment_invariant_alerts")
def run_payment_invariant_alerts(
    precheckout_stale_minutes: int = 3,
    paid_uncredited_stale_seconds: int = 60,
) -> dict[str, int]:
    return run_async_job(
        run_payment_invariant_alerts_async(
            precheckout_stale_minutes=precheckout_stale_minutes,
            paid_uncredited_stale_seconds=paid_uncredited_stale_seconds,
        )
    )


@celery_app.task(name="app.workers.tasks.payments_reliability.expire_stale_unpaid_invoices")
def expire_stale_unpaid_invoices(stale_minutes: int = 30) -> dict[str, int]:
    return run_tracked_async_job(
        task_name="app.workers.tasks.payments_reliability.expire_stale_unpaid_invoices",
        schedule_key="expire-stale-unpaid-invoices-every-5-minutes",
        awaitable=expire_stale_unpaid_invoices_async(stale_minutes=stale_minutes),
    )


@celery_app.task(name="app.workers.tasks.payments_reliability.run_refund_promo_rollback")
def run_refund_promo_rollback(batch_size: int = 100) -> dict[str, int]:
    return run_tracked_async_job(
        task_name="app.workers.tasks.payments_reliability.run_refund_promo_rollback",
        schedule_key="refund-promo-rollback-every-5-minutes",
        awaitable=run_refund_promo_rollback_async(batch_size=batch_size),
    )


@celery_app.task(name="app.workers.tasks.payments_reliability.run_payments_reconciliation")
def run_payments_reconciliation(stale_minutes: int = 30) -> dict[str, int | str]:
    return run_tracked_async_job(
        task_name="app.workers.tasks.payments_reliability.run_payments_reconciliation",
        schedule_key="payments-reconciliation-every-15-minutes",
        awaitable=run_payments_reconciliation_async(stale_minutes=stale_minutes),
    )


@celery_app.task(name="app.workers.tasks.payments_reliability.run_telegram_stars_reconciliation")
def run_telegram_stars_reconciliation() -> dict[str, object]:
    return run_tracked_async_job(
        task_name="app.workers.tasks.payments_reliability.run_telegram_stars_reconciliation",
        schedule_key="telegram-stars-reconciliation-every-5-minutes",
        awaitable=run_telegram_stars_reconciliation_async(),
    )


configure_payments_reliability_schedule(celery_app)
