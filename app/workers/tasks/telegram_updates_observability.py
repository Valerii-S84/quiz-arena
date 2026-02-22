from __future__ import annotations
from datetime import datetime, timedelta, timezone

import structlog

from app.core.config import get_settings
from app.db.repo.outbox_events_repo import OutboxEventsRepo
from app.db.repo.processed_updates_repo import ProcessedUpdatesRepo
from app.db.session import SessionLocal
from app.services.alerts import send_ops_alert
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.telegram_updates import (
    EVENT_TELEGRAM_UPDATE_FAILED_FINAL,
    EVENT_TELEGRAM_UPDATE_RECLAIMED,
    EVENT_TELEGRAM_UPDATE_RETRY_SCHEDULED,
)

logger = structlog.get_logger(__name__)


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


async def run_telegram_updates_reliability_alerts_async() -> dict[str, object]:
    settings = get_settings()
    processing_ttl_seconds = _clamp_int(
        settings.telegram_update_processing_ttl_seconds,
        minimum=1,
        maximum=86_400,
    )
    alert_window_minutes = _clamp_int(
        settings.telegram_updates_alert_window_minutes,
        minimum=1,
        maximum=1_440,
    )
    stuck_alert_min_minutes = _clamp_int(
        settings.telegram_updates_stuck_alert_min_minutes,
        minimum=1,
        maximum=1_440,
    )
    retry_spike_threshold = _clamp_int(
        settings.telegram_updates_retry_spike_threshold,
        minimum=0,
        maximum=1_000_000,
    )
    failed_final_spike_threshold = _clamp_int(
        settings.telegram_updates_failed_final_spike_threshold,
        minimum=0,
        maximum=1_000_000,
    )
    top_stuck_limit = _clamp_int(
        settings.telegram_updates_observability_top_stuck_limit,
        minimum=1,
        maximum=100,
    )

    now_utc = datetime.now(timezone.utc)
    since_utc = now_utc - timedelta(minutes=alert_window_minutes)
    stuck_threshold_seconds = max(
        processing_ttl_seconds,
        stuck_alert_min_minutes * 60,
    )

    event_types = (
        EVENT_TELEGRAM_UPDATE_RECLAIMED,
        EVENT_TELEGRAM_UPDATE_RETRY_SCHEDULED,
        EVENT_TELEGRAM_UPDATE_FAILED_FINAL,
    )
    async with SessionLocal.begin() as session:
        stuck_count = await ProcessedUpdatesRepo.count_processing_older_than_seconds(
            session,
            older_than_seconds=stuck_threshold_seconds,
        )
        max_age_seconds = await ProcessedUpdatesRepo.get_processing_age_max_seconds(session)
        oldest_processing = await ProcessedUpdatesRepo.list_oldest_processing(
            session,
            limit=top_stuck_limit,
        )
        event_counts = await OutboxEventsRepo.count_by_type_since(
            session,
            since_utc=since_utc,
            event_types=event_types,
        )

    reclaimed_total = int(event_counts.get(EVENT_TELEGRAM_UPDATE_RECLAIMED, 0))
    retries_total = int(event_counts.get(EVENT_TELEGRAM_UPDATE_RETRY_SCHEDULED, 0))
    failed_final_total = int(event_counts.get(EVENT_TELEGRAM_UPDATE_FAILED_FINAL, 0))

    stuck_detected = stuck_count > 0
    max_age_exceeded = max_age_seconds > (processing_ttl_seconds * 2)
    retries_spike_detected = retries_total > retry_spike_threshold
    failed_final_spike_detected = failed_final_total > failed_final_spike_threshold

    result: dict[str, object] = {
        "generated_at": now_utc.isoformat(),
        "window_minutes": alert_window_minutes,
        "processing_ttl_seconds": processing_ttl_seconds,
        "stuck_alert_min_minutes": stuck_alert_min_minutes,
        "processed_updates_processing_stuck_count": stuck_count,
        "processed_updates_processing_age_max_seconds": max_age_seconds,
        "telegram_updates_reclaimed_total": reclaimed_total,
        "telegram_updates_retries_total": retries_total,
        "telegram_updates_failed_final_total": failed_final_total,
        "retry_spike_threshold": retry_spike_threshold,
        "failed_final_spike_threshold": failed_final_spike_threshold,
        "alerts": {
            "stuck_detected": stuck_detected,
            "max_age_exceeded": max_age_exceeded,
            "retries_spike_detected": retries_spike_detected,
            "failed_final_spike_detected": failed_final_spike_detected,
        },
        "oldest_processing": oldest_processing,
    }

    if stuck_detected or max_age_exceeded or retries_spike_detected or failed_final_spike_detected:
        await send_ops_alert(
            event="telegram_updates_reliability_degraded",
            payload=result,
        )
        logger.warning("telegram_updates_reliability_alerts_detected", **result)
    else:
        logger.info("telegram_updates_reliability_alerts_ok", **result)

    return result


@celery_app.task(name="app.workers.tasks.telegram_updates_observability.run_telegram_updates_reliability_alerts")
def run_telegram_updates_reliability_alerts() -> dict[str, object]:
    return run_async_job(run_telegram_updates_reliability_alerts_async())


celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
celery_app.conf.beat_schedule.update(
    {
        "telegram-updates-reliability-alerts-every-5-minutes": {
            "task": "app.workers.tasks.telegram_updates_observability.run_telegram_updates_reliability_alerts",
            "schedule": 300.0,
            "options": {"queue": "q_normal"},
        },
    }
)
