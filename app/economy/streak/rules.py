from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from app.economy.streak.constants import (
    MONTHLY_PREMIUM_FREEZE_LIMIT,
    PREMIUM_SCOPE_SEASON,
    PREMIUM_SCOPE_STARTER,
    PREMIUM_SCOPE_YEAR,
)
from app.economy.streak.time import berlin_local_date, berlin_week_start
from app.economy.streak.types import StreakSnapshot, StreakStateLabel, StreakTodayStatus


def classify_streak_state(snapshot: StreakSnapshot) -> StreakStateLabel:
    if snapshot.today_status == StreakTodayStatus.PLAYED:
        return StreakStateLabel.ACTIVE_TODAY
    if snapshot.today_status == StreakTodayStatus.FROZEN:
        return StreakStateLabel.FROZEN_TODAY
    if snapshot.current_streak == 0:
        return StreakStateLabel.NO_STREAK
    return StreakStateLabel.AT_RISK


def _premium_freeze_allowed(snapshot: StreakSnapshot, day: date, premium_scope: str | None) -> bool:
    if premium_scope in {None, PREMIUM_SCOPE_STARTER}:
        return False
    if premium_scope in {PREMIUM_SCOPE_SEASON, PREMIUM_SCOPE_YEAR}:
        return True

    week_start = berlin_week_start(day)
    if snapshot.premium_freeze_week_start_local_date != week_start:
        return True
    return snapshot.premium_freezes_used_week < MONTHLY_PREMIUM_FREEZE_LIMIT


def _consume_premium_freeze(snapshot: StreakSnapshot, day: date) -> StreakSnapshot:
    week_start = berlin_week_start(day)
    used_week = snapshot.premium_freezes_used_week
    if snapshot.premium_freeze_week_start_local_date != week_start:
        used_week = 0

    return replace(
        snapshot,
        premium_freezes_used_week=used_week + 1,
        premium_freeze_week_start_local_date=week_start,
    )


def apply_day_end(
    snapshot: StreakSnapshot, *, day: date, premium_scope: str | None
) -> StreakSnapshot:
    if snapshot.today_status != StreakTodayStatus.NO_ACTIVITY:
        return snapshot

    if snapshot.current_streak <= 0:
        return snapshot

    if snapshot.streak_saver_tokens > 0:
        return replace(
            snapshot,
            streak_saver_tokens=snapshot.streak_saver_tokens - 1,
            today_status=StreakTodayStatus.FROZEN,
        )

    if _premium_freeze_allowed(snapshot, day, premium_scope):
        return replace(
            _consume_premium_freeze(snapshot, day),
            today_status=StreakTodayStatus.FROZEN,
        )

    return replace(snapshot, current_streak=0)


def rollover_to_local_date(
    snapshot: StreakSnapshot,
    *,
    target_local_date: date,
    premium_scope: str | None,
) -> StreakSnapshot:
    processed_local_date = berlin_local_date(snapshot.updated_at)
    if target_local_date <= processed_local_date:
        return snapshot

    updated = snapshot
    cursor = processed_local_date

    while cursor < target_local_date:
        updated = apply_day_end(updated, day=cursor, premium_scope=premium_scope)
        cursor = cursor + timedelta(days=1)
        updated = replace(updated, today_status=StreakTodayStatus.NO_ACTIVITY)

    return updated


def record_activity(snapshot: StreakSnapshot, *, local_date: date) -> tuple[StreakSnapshot, bool]:
    if (
        snapshot.last_activity_local_date == local_date
        and snapshot.today_status == StreakTodayStatus.PLAYED
    ):
        return snapshot, False

    if snapshot.current_streak <= 0:
        current_streak = 1
    else:
        current_streak = snapshot.current_streak + 1

    updated = replace(
        snapshot,
        current_streak=current_streak,
        best_streak=max(snapshot.best_streak, current_streak),
        last_activity_local_date=local_date,
        today_status=StreakTodayStatus.PLAYED,
    )
    return updated, True
