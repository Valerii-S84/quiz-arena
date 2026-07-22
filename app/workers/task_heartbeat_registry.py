from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CriticalTaskHeartbeat:
    task_name: str
    schedule_key: str
    stale_after_seconds: int
    severity: str = "P1"


CRITICAL_TASK_HEARTBEATS: tuple[CriticalTaskHeartbeat, ...] = (
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.payments_reliability.recover_paid_uncredited",
        schedule_key="recover-paid-uncredited-every-5-minutes",
        stale_after_seconds=600,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.payments_reliability.expire_stale_unpaid_invoices",
        schedule_key="expire-stale-unpaid-invoices-every-5-minutes",
        stale_after_seconds=600,
        severity="P2",
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.payments_reliability.run_refund_promo_rollback",
        schedule_key="refund-promo-rollback-every-5-minutes",
        stale_after_seconds=600,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.payments_reliability.run_payments_reconciliation",
        schedule_key="payments-reconciliation-every-15-minutes",
        stale_after_seconds=1800,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.payments_reliability.run_telegram_stars_reconciliation",
        schedule_key="telegram-stars-reconciliation-every-5-minutes",
        stale_after_seconds=600,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.payments_reliability.run_payments_reconciliation",
        schedule_key="payments-reconciliation-daily-0330-berlin",
        stale_after_seconds=172800,
    ),
    CriticalTaskHeartbeat(
        task_name="app.workers.tasks.analytics_daily.run_analytics_daily_aggregation",
        schedule_key="analytics-daily-aggregation-hourly",
        stale_after_seconds=7200,
        severity="P2",
    ),
)


def get_critical_task_heartbeats() -> tuple[CriticalTaskHeartbeat, ...]:
    return CRITICAL_TASK_HEARTBEATS
