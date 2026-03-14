from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.workers.tasks import admin_daily_metrics


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (-5, 1),
        (0, 1),
        (1, 1),
        (7, 7),
        (14, 14),
        (99, 14),
    ],
)
def test_clamp_days_back_enforces_worker_limits(raw_value: int, expected: int) -> None:
    assert admin_daily_metrics._clamp_days_back(raw_value) == expected


def test_day_bounds_utc_for_regular_berlin_day() -> None:
    start_utc, end_utc = admin_daily_metrics._day_bounds_utc(date(2026, 2, 15))

    assert start_utc == datetime(2026, 2, 14, 23, 0, tzinfo=timezone.utc)
    assert end_utc == datetime(2026, 2, 15, 23, 0, tzinfo=timezone.utc)


def test_day_bounds_utc_handles_dst_start_transition() -> None:
    start_utc, end_utc = admin_daily_metrics._day_bounds_utc(date(2026, 3, 29))

    assert start_utc == datetime(2026, 3, 28, 23, 0, tzinfo=timezone.utc)
    assert end_utc == datetime(2026, 3, 29, 22, 0, tzinfo=timezone.utc)


def test_run_admin_daily_metrics_aggregation_task_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_async(*, days_back: int) -> dict[str, object]:
        return {"days_processed": days_back, "dates": ["2026-04-10"]}

    monkeypatch.setattr(
        admin_daily_metrics, "run_admin_daily_metrics_aggregation_async", fake_async
    )

    result = admin_daily_metrics.run_admin_daily_metrics_aggregation(days_back=3)

    assert result == {"days_processed": 3, "dates": ["2026-04-10"]}
