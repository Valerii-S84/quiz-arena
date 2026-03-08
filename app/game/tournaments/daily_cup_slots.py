from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import get_settings

ROUND_SLOTS: tuple[tuple[int, int, int], ...] = (
    (18, 0, 30),
    (18, 30, 30),
    (19, 0, 30),
    (19, 30, 30),
)


def get_round_start(*, round_number: int, tournament_start: datetime) -> datetime:
    if round_number < 1 or round_number > len(ROUND_SLOTS):
        raise ValueError(round_number)
    tz = ZoneInfo(get_settings().daily_cup_timezone.strip() or "Europe/Berlin")
    local_start = tournament_start.astimezone(tz)
    hour, minute, _duration = ROUND_SLOTS[round_number - 1]
    resolved = local_start.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return resolved.astimezone(timezone.utc)


def get_round_deadline(*, round_number: int, tournament_start: datetime) -> datetime:
    round_start = get_round_start(round_number=round_number, tournament_start=tournament_start)
    _hour, _minute, duration_minutes = ROUND_SLOTS[round_number - 1]
    return (round_start + timedelta(minutes=duration_minutes)).replace(microsecond=0)
