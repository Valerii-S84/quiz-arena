from app.workers.tasks import analytics_daily


def test_run_analytics_daily_aggregation_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, days_back: int) -> dict[str, object]:
        return {"days_processed": days_back, "local_days_berlin": ["2026-02-20"]}

    monkeypatch.setattr(analytics_daily, "run_analytics_daily_aggregation_async", fake_async)

    result = analytics_daily.run_analytics_daily_aggregation(days_back=3)
    assert result == {"days_processed": 3, "local_days_berlin": ["2026-02-20"]}
