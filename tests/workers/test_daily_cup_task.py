from app.workers.tasks import daily_cup


def test_send_invite_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, int]:
        return {"processed": 1, "sent_total": 10}

    monkeypatch.setattr(daily_cup, "send_daily_cup_invite_async", fake_async)

    result = daily_cup.send_invite()
    assert result == {"processed": 1, "sent_total": 10}


def test_open_registration_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, int]:
        return {"processed": 1, "sent_total": 5}

    monkeypatch.setattr(daily_cup, "open_daily_cup_registration_async", fake_async)

    result = daily_cup.open_registration()
    assert result == {"processed": 1, "sent_total": 5}


def test_send_last_call_reminder_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, int]:
        return {"processed": 1, "sent_total": 4}

    monkeypatch.setattr(daily_cup, "send_daily_cup_last_call_reminder_async", fake_async)

    result = daily_cup.send_last_call_reminder()
    assert result == {"processed": 1, "sent_total": 4}


def test_send_prestart_reminder_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, int]:
        return {"processed": 1, "sent_total": 3}

    monkeypatch.setattr(daily_cup, "send_daily_cup_prestart_reminder_async", fake_async)

    result = daily_cup.send_prestart_reminder()
    assert result == {"processed": 1, "sent_total": 3}


def test_send_turn_reminders_task_wrapper(monkeypatch) -> None:
    async def fake_async() -> dict[str, int]:
        return {"processed": 1, "sent_total": 2, "queued_total": 2}

    monkeypatch.setattr(daily_cup, "run_daily_cup_turn_reminders_async", fake_async)

    result = daily_cup.send_turn_reminders()
    assert result == {"processed": 1, "sent_total": 2, "queued_total": 2}


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
