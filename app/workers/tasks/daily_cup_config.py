from __future__ import annotations

import os

from app.core.config import get_settings
from app.game.tournaments.constants import (
    TOURNAMENT_TYPE_DAILY_ARENA,
    TOURNAMENT_TYPE_DAILY_ELIMINATION,
)

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
_daily_cup_tournament_type = os.getenv("DAILY_CUP_TOURNAMENT_TYPE", TOURNAMENT_TYPE_DAILY_ARENA)
DAILY_CUP_TOURNAMENT_TYPE = (
    TOURNAMENT_TYPE_DAILY_ELIMINATION
    if _daily_cup_tournament_type.strip().upper() == TOURNAMENT_TYPE_DAILY_ELIMINATION
    else TOURNAMENT_TYPE_DAILY_ARENA
)
DAILY_CUP_INVITE_TIME = os.getenv("DAILY_CUP_INVITE_TIME", "16:00")
DAILY_CUP_LAST_CALL_REMINDER_TIME = os.getenv("DAILY_CUP_LAST_CALL_REMINDER_TIME", "17:30")
DAILY_CUP_PRESTART_REMINDER_TIME = os.getenv("DAILY_CUP_PRESTART_REMINDER_TIME", "17:45")
DAILY_CUP_REGISTRATION_OPEN = os.getenv("DAILY_CUP_OPEN_TIME", settings.daily_cup_registration_open)
DAILY_CUP_REGISTRATION_CLOSE = os.getenv(
    "DAILY_CUP_CLOSE_TIME", settings.daily_cup_registration_close
)
_round_minutes_raw = os.getenv("DAILY_CUP_ROUND_MINUTES")
DAILY_CUP_ROUND_DURATION_MINUTES = max(
    1,
    int(_round_minutes_raw or settings.daily_cup_round_duration_minutes),
)
DAILY_CUP_MIN_PARTICIPANTS = max(2, int(settings.daily_cup_min_participants))
DAILY_CUP_PUSH_BATCH_SIZE = 200
DAILY_CUP_ACTIVE_LOOKBACK_DAYS = 7
DAILY_CUP_TURN_REMINDER_INTERVAL_MINUTES = max(
    1,
    int(os.getenv("DAILY_CUP_TURN_REMINDER_INTERVAL_MINUTES", "10")),
)
DAILY_CUP_TURN_RESPONSE_GRACE_MINUTES = max(
    1,
    int(os.getenv("DAILY_CUP_TURN_RESPONSE_GRACE_MINUTES", "15")),
)
DAILY_CUP_DEFAULT_ADVANCE_SLOTS: tuple[tuple[int, int], ...] = ((19, 0), (20, 0), (21, 30))

DAILY_CUP_INVITE_HOUR, DAILY_CUP_INVITE_MINUTE = _parse_hhmm(
    DAILY_CUP_INVITE_TIME,
    default_hour=16,
    default_minute=0,
)
DAILY_CUP_LAST_CALL_REMINDER_HOUR, DAILY_CUP_LAST_CALL_REMINDER_MINUTE = _parse_hhmm(
    DAILY_CUP_LAST_CALL_REMINDER_TIME,
    default_hour=17,
    default_minute=30,
)
DAILY_CUP_PRESTART_REMINDER_HOUR, DAILY_CUP_PRESTART_REMINDER_MINUTE = _parse_hhmm(
    DAILY_CUP_PRESTART_REMINDER_TIME,
    default_hour=17,
    default_minute=45,
)

DAILY_CUP_OPEN_HOUR, DAILY_CUP_OPEN_MINUTE = _parse_hhmm(
    DAILY_CUP_REGISTRATION_OPEN,
    default_hour=17,
    default_minute=0,
)
DAILY_CUP_CLOSE_HOUR, DAILY_CUP_CLOSE_MINUTE = _parse_hhmm(
    DAILY_CUP_REGISTRATION_CLOSE,
    default_hour=18,
    default_minute=0,
)


def _parse_round_advance_slots(*, slots_value: str) -> tuple[tuple[int, int], ...]:
    slots: list[tuple[int, int]] = []
    for token in slots_value.split(","):
        hour, minute = _parse_hhmm(token, default_hour=-1, default_minute=-1)
        if hour < 0 or minute < 0:
            return DAILY_CUP_DEFAULT_ADVANCE_SLOTS
        slots.append((hour, minute))
    if not slots:
        return DAILY_CUP_DEFAULT_ADVANCE_SLOTS
    return tuple(slots)


DAILY_CUP_ROUND_ADVANCE_SLOTS = _parse_round_advance_slots(
    slots_value=os.getenv("DAILY_CUP_ADVANCE_SLOTS", "19:00,20:00,21:30")
)
DAILY_ELIMINATION_OPEN_TIME = os.getenv("DAILY_ELIMINATION_OPEN_TIME", "16:00")
DAILY_ELIMINATION_CLOSE_TIME = os.getenv("DAILY_ELIMINATION_CLOSE_TIME", "18:00")
DAILY_ELIMINATION_DEADLINE = os.getenv("DAILY_ELIMINATION_DEADLINE", "21:30")
DAILY_ELIMINATION_MATCH_TIMEOUT_MINUTES = max(
    1,
    int(os.getenv("DAILY_ELIMINATION_MATCH_TIMEOUT", "15")),
)
DAILY_ELIMINATION_MIN_PLAYERS = max(2, int(os.getenv("DAILY_ELIMINATION_MIN_PLAYERS", "4")))
DAILY_ELIMINATION_OPEN_HOUR, DAILY_ELIMINATION_OPEN_MINUTE = _parse_hhmm(
    DAILY_ELIMINATION_OPEN_TIME,
    default_hour=16,
    default_minute=0,
)
DAILY_ELIMINATION_CLOSE_HOUR, DAILY_ELIMINATION_CLOSE_MINUTE = _parse_hhmm(
    DAILY_ELIMINATION_CLOSE_TIME,
    default_hour=18,
    default_minute=0,
)
DAILY_ELIMINATION_DEADLINE_HOUR, DAILY_ELIMINATION_DEADLINE_MINUTE = _parse_hhmm(
    DAILY_ELIMINATION_DEADLINE,
    default_hour=21,
    default_minute=30,
)

__all__ = [
    "DAILY_CUP_ACTIVE_LOOKBACK_DAYS",
    "DAILY_CUP_CLOSE_HOUR",
    "DAILY_CUP_CLOSE_MINUTE",
    "DAILY_CUP_INVITE_HOUR",
    "DAILY_CUP_INVITE_MINUTE",
    "DAILY_CUP_LAST_CALL_REMINDER_HOUR",
    "DAILY_CUP_LAST_CALL_REMINDER_MINUTE",
    "DAILY_CUP_PRESTART_REMINDER_HOUR",
    "DAILY_CUP_PRESTART_REMINDER_MINUTE",
    "DAILY_CUP_MIN_PARTICIPANTS",
    "DAILY_CUP_OPEN_HOUR",
    "DAILY_CUP_OPEN_MINUTE",
    "DAILY_CUP_PUSH_BATCH_SIZE",
    "DAILY_CUP_ROUND_ADVANCE_SLOTS",
    "DAILY_CUP_ROUND_DURATION_MINUTES",
    "DAILY_CUP_TURN_RESPONSE_GRACE_MINUTES",
    "DAILY_CUP_TOURNAMENT_TYPE",
    "DAILY_CUP_TURN_REMINDER_INTERVAL_MINUTES",
    "DAILY_CUP_TIMEZONE",
    "DAILY_ELIMINATION_CLOSE_HOUR",
    "DAILY_ELIMINATION_CLOSE_MINUTE",
    "DAILY_ELIMINATION_DEADLINE_HOUR",
    "DAILY_ELIMINATION_DEADLINE_MINUTE",
    "DAILY_ELIMINATION_MATCH_TIMEOUT_MINUTES",
    "DAILY_ELIMINATION_MIN_PLAYERS",
    "DAILY_ELIMINATION_OPEN_HOUR",
    "DAILY_ELIMINATION_OPEN_MINUTE",
]
