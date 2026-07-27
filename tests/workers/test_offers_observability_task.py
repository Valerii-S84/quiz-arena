from app.workers.tasks import offers_observability


def test_run_offers_funnel_alerts_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, object]:
        return {"status": "ok", "impressions_total": 42}

    monkeypatch.setattr(offers_observability, "run_offers_funnel_alerts_async", fake_async)

    result = offers_observability.run_offers_funnel_alerts()
    assert result == {"status": "ok", "impressions_total": 42}
