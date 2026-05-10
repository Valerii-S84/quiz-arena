from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.workers.tasks import admin_daily_metrics


def test_run_admin_daily_metrics_aggregation_async_upserts_days(
    monkeypatch,
) -> None:
    executed: list[object] = []

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 10, 12, 0, tzinfo=UTC).astimezone(tz)

        @classmethod
        def combine(cls, *args, **kwargs):
            return datetime.combine(*args, **kwargs)

    class Result:
        def __init__(self, value: int) -> None:
            self.value = value

        def scalar_one(self) -> int:
            return self.value

    class Session:
        async def execute(self, stmt):
            executed.append(stmt)
            return Result(len(executed))

    class SessionLocal:
        def begin(self):
            return _AsyncContext(Session())

    async def _count_active(_session, **_kwargs) -> int:
        return 7

    monkeypatch.setattr(admin_daily_metrics, "datetime", FixedDatetime)
    monkeypatch.setattr(admin_daily_metrics, "SessionLocal", SessionLocal())
    monkeypatch.setattr(admin_daily_metrics, "_count_active_users", _count_active)

    result = asyncio.run(admin_daily_metrics.run_admin_daily_metrics_aggregation_async(days_back=2))

    assert result["days_processed"] == 2
    assert result["dates"] == ["2026-05-10", "2026-05-09"]
    assert len(executed) == 12


class _AsyncContext:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False
