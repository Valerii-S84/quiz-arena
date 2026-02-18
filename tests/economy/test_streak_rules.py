from __future__ import annotations

from datetime import date, datetime, timezone

from app.economy.streak.constants import PREMIUM_SCOPE_MONTH, PREMIUM_SCOPE_SEASON, PREMIUM_SCOPE_STARTER
from app.economy.streak.rules import (
    apply_day_end,
    classify_streak_state,
    record_activity,
    rollover_to_local_date,
)
from app.economy.streak.time import berlin_local_date, berlin_week_start
from app.economy.streak.types import StreakSnapshot, StreakStateLabel, StreakTodayStatus


UTC = timezone.utc


def snapshot(
    *,
    current_streak: int,
    best_streak: int,
    today_status: StreakTodayStatus,
    updated_at: datetime,
    last_activity_local_date: date | None = None,
    streak_saver_tokens: int = 0,
    premium_freezes_used_week: int = 0,
    premium_freeze_week_start_local_date: date | None = None,
) -> StreakSnapshot:
    return StreakSnapshot(
        current_streak=current_streak,
        best_streak=best_streak,
        last_activity_local_date=last_activity_local_date,
        today_status=today_status,
        streak_saver_tokens=streak_saver_tokens,
        premium_freezes_used_week=premium_freezes_used_week,
        premium_freeze_week_start_local_date=premium_freeze_week_start_local_date,
        updated_at=updated_at,
    )


def test_transition_no_streak_to_active_today_on_activity() -> None:
    day = date(2026, 2, 17)
    state_before = snapshot(
        current_streak=0,
        best_streak=3,
        today_status=StreakTodayStatus.NO_ACTIVITY,
        updated_at=datetime(2026, 2, 17, 10, 0, tzinfo=UTC),
    )

    state_after, counted = record_activity(state_before, local_date=day)

    assert counted is True
    assert state_after.current_streak == 1
    assert state_after.best_streak == 3
    assert state_after.last_activity_local_date == day
    assert classify_streak_state(state_after) == StreakStateLabel.ACTIVE_TODAY


def test_transition_active_today_to_at_risk_on_day_start() -> None:
    day = date(2026, 2, 17)
    state_before = snapshot(
        current_streak=5,
        best_streak=7,
        today_status=StreakTodayStatus.PLAYED,
        updated_at=datetime(2026, 2, 17, 12, 0, tzinfo=UTC),
        last_activity_local_date=day,
    )

    state_after = rollover_to_local_date(
        state_before,
        target_local_date=date(2026, 2, 18),
        premium_scope=None,
    )

    assert state_after.current_streak == 5
    assert state_after.today_status == StreakTodayStatus.NO_ACTIVITY
    assert classify_streak_state(state_after) == StreakStateLabel.AT_RISK


def test_transition_at_risk_to_active_today_on_activity() -> None:
    day = date(2026, 2, 18)
    state_before = snapshot(
        current_streak=5,
        best_streak=7,
        today_status=StreakTodayStatus.NO_ACTIVITY,
        updated_at=datetime(2026, 2, 18, 1, 0, tzinfo=UTC),
        last_activity_local_date=date(2026, 2, 17),
    )

    state_after, counted = record_activity(state_before, local_date=day)

    assert counted is True
    assert state_after.current_streak == 6
    assert state_after.best_streak == 7
    assert classify_streak_state(state_after) == StreakStateLabel.ACTIVE_TODAY


def test_transition_at_risk_to_frozen_today_with_saver() -> None:
    state_before = snapshot(
        current_streak=8,
        best_streak=9,
        today_status=StreakTodayStatus.NO_ACTIVITY,
        streak_saver_tokens=1,
        updated_at=datetime(2026, 2, 18, 20, 0, tzinfo=UTC),
    )

    state_after = apply_day_end(state_before, day=date(2026, 2, 18), premium_scope=None)

    assert state_after.current_streak == 8
    assert state_after.streak_saver_tokens == 0
    assert state_after.today_status == StreakTodayStatus.FROZEN
    assert classify_streak_state(state_after) == StreakStateLabel.FROZEN_TODAY


def test_transition_at_risk_to_frozen_today_with_premium() -> None:
    state_before = snapshot(
        current_streak=8,
        best_streak=9,
        today_status=StreakTodayStatus.NO_ACTIVITY,
        updated_at=datetime(2026, 2, 18, 20, 0, tzinfo=UTC),
    )

    state_after = apply_day_end(
        state_before,
        day=date(2026, 2, 18),
        premium_scope=PREMIUM_SCOPE_MONTH,
    )

    assert state_after.current_streak == 8
    assert state_after.premium_freezes_used_week == 1
    assert state_after.today_status == StreakTodayStatus.FROZEN


def test_transition_at_risk_to_no_streak_without_freeze() -> None:
    state_before = snapshot(
        current_streak=8,
        best_streak=9,
        today_status=StreakTodayStatus.NO_ACTIVITY,
        updated_at=datetime(2026, 2, 18, 20, 0, tzinfo=UTC),
    )

    state_after = apply_day_end(state_before, day=date(2026, 2, 18), premium_scope=PREMIUM_SCOPE_STARTER)

    assert state_after.current_streak == 0
    assert state_after.today_status == StreakTodayStatus.NO_ACTIVITY
    assert classify_streak_state(state_after) == StreakStateLabel.NO_STREAK


def test_transition_frozen_today_to_at_risk_on_day_start() -> None:
    state_before = snapshot(
        current_streak=5,
        best_streak=7,
        today_status=StreakTodayStatus.FROZEN,
        updated_at=datetime(2026, 2, 18, 20, 0, tzinfo=UTC),
    )

    state_after = rollover_to_local_date(
        state_before,
        target_local_date=date(2026, 2, 19),
        premium_scope=None,
    )

    assert state_after.current_streak == 5
    assert state_after.today_status == StreakTodayStatus.NO_ACTIVITY
    assert classify_streak_state(state_after) == StreakStateLabel.AT_RISK


def test_month_premium_freeze_limited_per_week() -> None:
    monday = date(2026, 2, 16)
    state_before = snapshot(
        current_streak=5,
        best_streak=5,
        today_status=StreakTodayStatus.NO_ACTIVITY,
        updated_at=datetime(2026, 2, 16, 12, 0, tzinfo=UTC),
    )

    state_after = rollover_to_local_date(
        state_before,
        target_local_date=date(2026, 2, 18),
        premium_scope=PREMIUM_SCOPE_MONTH,
    )

    assert state_after.current_streak == 0
    assert state_after.premium_freezes_used_week == 1
    assert state_after.premium_freeze_week_start_local_date == monday


def test_season_premium_freeze_is_unlimited() -> None:
    state_before = snapshot(
        current_streak=5,
        best_streak=5,
        today_status=StreakTodayStatus.NO_ACTIVITY,
        updated_at=datetime(2026, 2, 16, 12, 0, tzinfo=UTC),
    )

    state_after = rollover_to_local_date(
        state_before,
        target_local_date=date(2026, 2, 20),
        premium_scope=PREMIUM_SCOPE_SEASON,
    )

    assert state_after.current_streak == 5
    assert state_after.today_status == StreakTodayStatus.NO_ACTIVITY


def test_record_activity_same_day_is_idempotent() -> None:
    day = date(2026, 2, 18)
    state_before = snapshot(
        current_streak=6,
        best_streak=8,
        today_status=StreakTodayStatus.PLAYED,
        updated_at=datetime(2026, 2, 18, 12, 0, tzinfo=UTC),
        last_activity_local_date=day,
    )

    state_after, counted = record_activity(state_before, local_date=day)

    assert counted is False
    assert state_after.current_streak == 6
    assert state_after.best_streak == 8


def test_berlin_day_and_week_helpers_with_dst() -> None:
    assert berlin_local_date(datetime(2026, 3, 28, 23, 30, tzinfo=UTC)) == date(2026, 3, 29)
    assert berlin_local_date(datetime(2026, 10, 25, 0, 30, tzinfo=UTC)) == date(2026, 10, 25)
    assert berlin_week_start(date(2026, 10, 25)) == date(2026, 10, 19)
