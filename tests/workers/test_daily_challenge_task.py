from app.workers.tasks import daily_challenge


def test_run_daily_question_set_precompute_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, object]:
        return {"berlin_date": "2026-02-26", "questions_total": 7}

    monkeypatch.setattr(daily_challenge, "run_daily_question_set_precompute_async", fake_async)

    result = daily_challenge.run_daily_question_set_precompute()
    assert result == {"berlin_date": "2026-02-26", "questions_total": 7}


def test_run_daily_push_notifications_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, batch_size: int) -> dict[str, object]:
        return {"batch_size": batch_size, "sent_total": 5, "skipped_total": 1}

    monkeypatch.setattr(daily_challenge, "run_daily_push_notifications_async", fake_async)

    result = daily_challenge.run_daily_push_notifications(batch_size=50)
    assert result == {"batch_size": 50, "sent_total": 5, "skipped_total": 1}
