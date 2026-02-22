from app.workers.tasks import telegram_updates_observability


def test_run_telegram_updates_reliability_alerts_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, object]:
        return {
            "processed_updates_processing_stuck_count": 1,
            "processed_updates_processing_age_max_seconds": 900,
            "telegram_updates_reclaimed_total": 2,
            "telegram_updates_retries_total": 4,
            "telegram_updates_failed_final_total": 1,
        }

    monkeypatch.setattr(
        telegram_updates_observability,
        "run_telegram_updates_reliability_alerts_async",
        fake_async,
    )

    result = telegram_updates_observability.run_telegram_updates_reliability_alerts()
    assert result["processed_updates_processing_stuck_count"] == 1
    assert result["telegram_updates_retries_total"] == 4
