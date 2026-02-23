from __future__ import annotations

from celery.schedules import crontab


def configure_payments_reliability_schedule(celery_app) -> None:
    celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
    celery_app.conf.beat_schedule.update(
        {
            "recover-paid-uncredited-every-5-minutes": {
                "task": "app.workers.tasks.payments_reliability.recover_paid_uncredited",
                "schedule": 300.0,
                "options": {"queue": "q_high"},
            },
            "expire-stale-unpaid-invoices-every-5-minutes": {
                "task": "app.workers.tasks.payments_reliability.expire_stale_unpaid_invoices",
                "schedule": 300.0,
                "options": {"queue": "q_normal"},
            },
            "refund-promo-rollback-every-5-minutes": {
                "task": "app.workers.tasks.payments_reliability.run_refund_promo_rollback",
                "schedule": 300.0,
                "options": {"queue": "q_normal"},
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
