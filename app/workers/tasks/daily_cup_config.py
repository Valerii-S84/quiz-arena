from __future__ import annotations

from datetime import datetime, timedelta

from app.core.config import get_settings

settings = get_settings()


def _parse_hhmm(value: str, *, default_hour: int, default_minute: int) -> tuple[int, int]:
    try:
        hour_raw, minute_raw = value.strip().split(":", maxsplit=1)
        hour = int(hour_raw)
        minute = int(minute_raw)
    except (AttributeError, ValueError):
        return default_hour, default_minute
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return default_hour, default_minute
    return hour, minute


DAILY_CUP_TIMEZONE = settings.daily_cup_timezone.strip() or "Europe/Berlin"
DAILY_CUP_REGISTRATION_OPEN = settings.daily_cup_registration_open
DAILY_CUP_REGISTRATION_CLOSE = settings.daily_cup_registration_close
DAILY_CUP_ROUND_DURATION_MINUTES = max(1, int(settings.daily_cup_round_duration_minutes))
DAILY_CUP_MIN_PARTICIPANTS = max(2, int(settings.daily_cup_min_participants))
DAILY_CUP_PUSH_BATCH_SIZE = 200
DAILY_CUP_ACTIVE_LOOKBACK_DAYS = 7

DAILY_CUP_OPEN_HOUR, DAILY_CUP_OPEN_MINUTE = _parse_hhmm(
    DAILY_CUP_REGISTRATION_OPEN,
    default_hour=12,
    default_minute=0,
)
DAILY_CUP_CLOSE_HOUR, DAILY_CUP_CLOSE_MINUTE = _parse_hhmm(
    DAILY_CUP_REGISTRATION_CLOSE,
    default_hour=14,
    default_minute=0,
)


def _build_round_advance_slots(*, rounds: int = 3) -> tuple[tuple[int, int], ...]:
    anchor = datetime(2000, 1, 1, DAILY_CUP_CLOSE_HOUR, DAILY_CUP_CLOSE_MINUTE)
    slots: list[tuple[int, int]] = []
    for round_no in range(1, max(1, rounds) + 1):
        slot = anchor + timedelta(minutes=DAILY_CUP_ROUND_DURATION_MINUTES * round_no)
        slots.append((int(slot.hour), int(slot.minute)))
    return tuple(slots)


DAILY_CUP_ROUND_ADVANCE_SLOTS = _build_round_advance_slots()

__all__ = [
    "DAILY_CUP_ACTIVE_LOOKBACK_DAYS",
    "DAILY_CUP_CLOSE_HOUR",
    "DAILY_CUP_CLOSE_MINUTE",
    "DAILY_CUP_MIN_PARTICIPANTS",
    "DAILY_CUP_OPEN_HOUR",
    "DAILY_CUP_OPEN_MINUTE",
    "DAILY_CUP_PUSH_BATCH_SIZE",
    "DAILY_CUP_ROUND_ADVANCE_SLOTS",
    "DAILY_CUP_ROUND_DURATION_MINUTES",
    "DAILY_CUP_TIMEZONE",
]
