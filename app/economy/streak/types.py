from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class StreakTodayStatus(str, Enum):
    NO_ACTIVITY = "NO_ACTIVITY"
    PLAYED = "PLAYED"
    FROZEN = "FROZEN"


class StreakStateLabel(str, Enum):
    NO_STREAK = "S_NO_STREAK"
    ACTIVE_TODAY = "S_ACTIVE_TODAY"
    AT_RISK = "S_AT_RISK"
    FROZEN_TODAY = "S_FROZEN_TODAY"


@dataclass(slots=True)
class StreakSnapshot:
    current_streak: int
    best_streak: int
    last_activity_local_date: date | None
    today_status: StreakTodayStatus
    streak_saver_tokens: int
    premium_freezes_used_week: int
    premium_freeze_week_start_local_date: date | None
    updated_at: datetime


@dataclass(slots=True)
class StreakActivityResult:
    counted_for_streak: bool
    current_streak: int
    best_streak: int
    today_status: StreakTodayStatus
    state: StreakStateLabel
