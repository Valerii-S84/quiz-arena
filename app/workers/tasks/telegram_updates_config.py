from __future__ import annotations

from app.core.config import get_settings

settings = get_settings()

PROCESSING_TTL_SECONDS = max(1, int(settings.telegram_update_processing_ttl_seconds))
TASK_MAX_RETRIES = max(0, int(settings.telegram_update_task_max_retries))
TASK_RETRY_BACKOFF_MAX_SECONDS = max(
    1, int(settings.telegram_update_task_retry_backoff_max_seconds)
)
RETRY_JITTER_RATIO = 0.25

EVENT_TELEGRAM_UPDATE_RECLAIMED = "telegram_update_reclaimed"
EVENT_TELEGRAM_UPDATE_RETRY_SCHEDULED = "telegram_update_retry_scheduled"
EVENT_TELEGRAM_UPDATE_FAILED_FINAL = "telegram_update_failed_final"

_ACQUIRE_CREATED = "created"
_ACQUIRE_RECLAIMED_FAILED = "reclaimed_failed"
_ACQUIRE_RECLAIMED_STALE = "reclaimed_stale"
_ACQUIRE_DUPLICATE = "duplicate"

__all__ = [
    "EVENT_TELEGRAM_UPDATE_FAILED_FINAL",
    "EVENT_TELEGRAM_UPDATE_RECLAIMED",
    "EVENT_TELEGRAM_UPDATE_RETRY_SCHEDULED",
    "PROCESSING_TTL_SECONDS",
    "RETRY_JITTER_RATIO",
    "TASK_MAX_RETRIES",
    "TASK_RETRY_BACKOFF_MAX_SECONDS",
    "_ACQUIRE_CREATED",
    "_ACQUIRE_DUPLICATE",
    "_ACQUIRE_RECLAIMED_FAILED",
    "_ACQUIRE_RECLAIMED_STALE",
]
