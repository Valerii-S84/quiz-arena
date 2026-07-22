from app.workers.asyncio_runner import run_async_job
from app.workers.tasks import offers_observability


def test_run_offers_funnel_alerts_task_wrapper(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def fake_async() -> dict[str, object]:
        return {"status": "ok", "impressions_total": 42}

    def run_tracked(*, task_name, schedule_key, awaitable):
        captured.update(task_name=task_name, schedule_key=schedule_key)
        return run_async_job(awaitable)

    monkeypatch.setattr(offers_observability, "run_offers_funnel_alerts_async", fake_async)
    monkeypatch.setattr(offers_observability, "run_tracked_async_job", run_tracked)

    result = offers_observability.run_offers_funnel_alerts()
    assert result == {"status": "ok", "impressions_total": 42}
    assert captured == {
        "task_name": "app.workers.tasks.offers_observability.run_offers_funnel_alerts",
        "schedule_key": "offers-funnel-alerts-every-15-minutes",
    }
