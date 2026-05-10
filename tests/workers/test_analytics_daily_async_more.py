from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.workers.tasks import analytics_daily
from tests.workers.payments_reliability_async_support import SessionLocalStub


def test_run_analytics_daily_aggregation_async_processes_clamped_days(
    monkeypatch,
) -> None:
    rows: list[object] = []
    requested_days: list[date] = []

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 10, 12, 0, tzinfo=UTC).astimezone(tz)

    async def _snapshot(_session, *, local_date_berlin, now_utc):
        requested_days.append(local_date_berlin)
        return SimpleNamespace(row={"day": local_date_berlin.isoformat(), "now": now_utc})

    async def _upsert(_session, *, row) -> None:
        rows.append(row)

    monkeypatch.setattr(analytics_daily, "datetime", FixedDatetime)
    monkeypatch.setattr(analytics_daily, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(analytics_daily, "build_daily_snapshot", _snapshot)
    monkeypatch.setattr(analytics_daily.AnalyticsRepo, "upsert_daily", _upsert)

    result = asyncio.run(analytics_daily.run_analytics_daily_aggregation_async(days_back=99))

    assert result["days_processed"] == 14
    assert result["local_days_berlin"] == [day.isoformat() for day in requested_days]
    assert len(rows) == 14


def test_analytics_daily_clamp_bounds() -> None:
    assert analytics_daily._clamp_days_back(0) == 1
    assert analytics_daily._clamp_days_back(99) == 14
