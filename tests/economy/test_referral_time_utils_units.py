from __future__ import annotations

from datetime import datetime, timezone

from app.economy.referrals.service import time_utils

UTC = timezone.utc


def test_berlin_day_bounds_handle_dst_transition() -> None:
    now_utc = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)

    day_start_utc, day_end_utc = time_utils._berlin_day_bounds_utc(now_utc)

    assert day_start_utc == datetime(2026, 3, 28, 23, 0, tzinfo=UTC)
    assert day_end_utc == datetime(2026, 3, 29, 22, 0, tzinfo=UTC)


def test_berlin_month_bounds_handle_december_rollover() -> None:
    now_utc = datetime(2026, 12, 15, 12, 0, tzinfo=UTC)

    month_start_utc, next_month_start_utc = time_utils._berlin_month_bounds_utc(now_utc)

    assert month_start_utc == datetime(2026, 11, 30, 23, 0, tzinfo=UTC)
    assert next_month_start_utc == datetime(2026, 12, 31, 23, 0, tzinfo=UTC)
