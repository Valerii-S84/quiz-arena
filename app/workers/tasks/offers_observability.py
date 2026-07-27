from __future__ import annotations

from datetime import datetime, timezone

import structlog

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.alerts import send_ops_alert
from app.services.offers_observability import (
    build_offer_funnel_snapshot,
    evaluate_offer_alert_state,
    get_offer_alert_thresholds,
)
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _clamp_window_hours(value: int) -> int:
    return max(1, min(168, int(value)))


async def run_offers_funnel_alerts_async() -> dict[str, object]:
    settings = get_settings()
    now_utc = datetime.now(timezone.utc)
    window_hours = _clamp_window_hours(settings.offers_alert_window_hours)
    thresholds = get_offer_alert_thresholds(settings)

    async with SessionLocal.begin() as session:
        snapshot = await build_offer_funnel_snapshot(
            session,
            now_utc=now_utc,
            window_hours=window_hours,
        )

    alert_state = evaluate_offer_alert_state(
        snapshot=snapshot,
        thresholds=thresholds,
    )

    result: dict[str, object] = {
        "generated_at": snapshot.generated_at.isoformat(),
        "window_hours": snapshot.window_hours,
        "impressions_total": snapshot.impressions_total,
        "unique_users": snapshot.unique_users,
        "clicks_total": snapshot.clicks_total,
        "dismissals_total": snapshot.dismissals_total,
        "conversions_total": snapshot.conversions_total,
        "click_through_rate": snapshot.click_through_rate,
        "conversion_rate": snapshot.conversion_rate,
        "dismiss_rate": snapshot.dismiss_rate,
        "impressions_per_user": snapshot.impressions_per_user,
        "top_offer_codes": snapshot.top_offer_codes,
        "thresholds": {
            "min_impressions": thresholds.min_impressions,
            "min_conversion_rate": thresholds.min_conversion_rate,
            "max_dismiss_rate": thresholds.max_dismiss_rate,
            "max_impressions_per_user": thresholds.max_impressions_per_user,
        },
        "alerts": {
            "thresholds_applied": alert_state.thresholds_applied,
            "conversion_drop_detected": alert_state.conversion_drop_detected,
            "spam_anomaly_detected": alert_state.spam_anomaly_detected,
            "conversion_rate_below_threshold": alert_state.conversion_rate_below_threshold,
            "dismiss_rate_above_threshold": alert_state.dismiss_rate_above_threshold,
            "impressions_per_user_above_threshold": alert_state.impressions_per_user_above_threshold,
        },
    }

    if alert_state.conversion_drop_detected:
        await send_ops_alert(
            event="offers_conversion_drop_detected",
            payload=result,
        )

    if alert_state.spam_anomaly_detected:
        await send_ops_alert(
            event="offers_spam_anomaly_detected",
            payload=result,
        )

    if alert_state.conversion_drop_detected or alert_state.spam_anomaly_detected:
        logger.warning("offers_funnel_alerts_detected", **result)
    else:
        logger.info("offers_funnel_alerts_ok", **result)

    return result


@celery_app.task(name="app.workers.tasks.offers_observability.run_offers_funnel_alerts")
def run_offers_funnel_alerts() -> dict[str, object]:
    return run_async_job(run_offers_funnel_alerts_async())


celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
celery_app.conf.beat_schedule.update(
    {
        "offers-funnel-alerts-every-15-minutes": {
            "task": "app.workers.tasks.offers_observability.run_offers_funnel_alerts",
            "schedule": 900.0,
            "options": {"queue": "q_normal"},
        },
    }
)
