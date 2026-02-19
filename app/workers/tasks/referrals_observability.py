from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.alerts import send_ops_alert
from app.services.referrals_observability import (
    build_referrals_dashboard_snapshot,
    evaluate_referrals_alert_state,
    get_referrals_alert_thresholds,
)
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _clamp_window_hours(value: int) -> int:
    return max(1, min(168, int(value)))


async def run_referrals_fraud_alerts_async() -> dict[str, object]:
    settings = get_settings()
    now_utc = datetime.now(timezone.utc)
    window_hours = _clamp_window_hours(settings.referrals_alert_window_hours)
    thresholds = get_referrals_alert_thresholds(settings)

    async with SessionLocal.begin() as session:
        snapshot = await build_referrals_dashboard_snapshot(
            session,
            now_utc=now_utc,
            window_hours=window_hours,
        )

    alert_state = evaluate_referrals_alert_state(snapshot=snapshot, thresholds=thresholds)
    result: dict[str, object] = {
        "generated_at": snapshot.generated_at.isoformat(),
        "window_hours": snapshot.window_hours,
        "referrals_started_total": snapshot.referrals_started_total,
        "qualified_like_total": snapshot.qualified_like_total,
        "rewarded_total": snapshot.rewarded_total,
        "rejected_fraud_total": snapshot.rejected_fraud_total,
        "canceled_total": snapshot.canceled_total,
        "qualification_rate": snapshot.qualification_rate,
        "reward_rate": snapshot.reward_rate,
        "fraud_rejected_rate": snapshot.fraud_rejected_rate,
        "status_counts": snapshot.status_counts,
        "top_referrers": snapshot.top_referrers,
        "recent_fraud_cases": snapshot.recent_fraud_cases,
        "thresholds": {
            "min_started": thresholds.min_started,
            "max_fraud_rejected_rate": thresholds.max_fraud_rejected_rate,
            "max_rejected_fraud_total": thresholds.max_rejected_fraud_total,
            "max_referrer_rejected_fraud": thresholds.max_referrer_rejected_fraud,
        },
        "alerts": {
            "thresholds_applied": alert_state.thresholds_applied,
            "fraud_spike_detected": alert_state.fraud_spike_detected,
            "fraud_rate_above_threshold": alert_state.fraud_rate_above_threshold,
            "rejected_fraud_total_above_threshold": alert_state.rejected_fraud_total_above_threshold,
            "referrer_spike_detected": alert_state.referrer_spike_detected,
        },
    }

    if alert_state.fraud_spike_detected:
        await send_ops_alert(
            event="referral_fraud_spike_detected",
            payload=result,
        )
        logger.warning("referrals_fraud_alerts_detected", **result)
    else:
        logger.info("referrals_fraud_alerts_ok", **result)

    return result


@celery_app.task(name="app.workers.tasks.referrals_observability.run_referrals_fraud_alerts")
def run_referrals_fraud_alerts() -> dict[str, object]:
    return asyncio.run(run_referrals_fraud_alerts_async())


celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
celery_app.conf.beat_schedule.update(
    {
        "referrals-fraud-alerts-every-15-minutes": {
            "task": "app.workers.tasks.referrals_observability.run_referrals_fraud_alerts",
            "schedule": 900.0,
            "options": {"queue": "q_normal"},
        },
    }
)
