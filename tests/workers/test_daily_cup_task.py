from app.workers.tasks import daily_cup


def test_open_registration_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, int]:
        return {"processed": 1, "sent_total": 5}

    monkeypatch.setattr(daily_cup, "open_daily_cup_registration_async", fake_async)

    result = daily_cup.open_registration()
    assert result == {"processed": 1, "sent_total": 5}


def test_close_registration_and_start_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, int]:
        return {"processed": 1, "canceled": 0, "started": 1}

    monkeypatch.setattr(daily_cup, "close_daily_cup_registration_and_start_async", fake_async)

    result = daily_cup.close_registration_and_start()
    assert result == {"processed": 1, "canceled": 0, "started": 1}


def test_advance_rounds_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, int]:
        return {"processed": 1, "rounds_started_total": 2}

    monkeypatch.setattr(daily_cup, "advance_daily_cup_rounds_async", fake_async)

    result = daily_cup.advance_rounds()
    assert result == {"processed": 1, "rounds_started_total": 2}
