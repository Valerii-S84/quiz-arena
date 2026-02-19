from app.workers.tasks import referrals_observability


def test_run_referrals_fraud_alerts_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, object]:
        return {"status": "ok", "referrals_started_total": 10}

    monkeypatch.setattr(referrals_observability, "run_referrals_fraud_alerts_async", fake_async)

    result = referrals_observability.run_referrals_fraud_alerts()
    assert result == {"status": "ok", "referrals_started_total": 10}
