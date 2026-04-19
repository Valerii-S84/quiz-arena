from __future__ import annotations

from celery.schedules import crontab


def clamp_retention_days(value: int) -> int:
    return max(1, min(3650, int(value)))


def clamp_batch_size(value: int) -> int:
    return max(1, min(50000, int(value)))


def clamp_max_batches(value: int) -> int:
    return max(1, min(1000, int(value)))


def clamp_schedule_seconds(value: int) -> int:
    return max(0, min(86400, int(value)))


def clamp_runtime_seconds(value: int) -> int:
    return max(5, min(600, int(value)))


def resolve_sleep_range_ms(*, minimum: int, maximum: int) -> tuple[int, int]:
    resolved_min = max(0, min(5000, int(minimum)))
    resolved_max = max(0, min(5000, int(maximum)))
    if resolved_max < resolved_min:
        return (resolved_max, resolved_min)
    return (resolved_min, resolved_max)


def clamp_schedule_hour(value: int) -> int:
    return max(0, min(23, int(value)))


def clamp_schedule_minute(value: int) -> int:
    return max(0, min(59, int(value)))


def resolve_cleanup_schedule(settings) -> int | crontab:
    schedule_seconds = clamp_schedule_seconds(settings.retention_cleanup_schedule_seconds)
    if schedule_seconds > 0:
        return schedule_seconds
    return crontab(
        hour=clamp_schedule_hour(settings.retention_cleanup_schedule_hour_berlin),
        minute=clamp_schedule_minute(settings.retention_cleanup_schedule_minute_berlin),
    )
