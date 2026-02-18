from app.workers.tasks import telegram_updates


def test_process_telegram_update_returns_ignored_when_update_id_missing() -> None:
    result = telegram_updates.process_telegram_update(update_payload={"message": {"message_id": 1}})
    assert result == "ignored"


def test_process_telegram_update_uses_extracted_update_id(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_process_update_async(
        update_payload: dict[str, object],
        *,
        update_id: int,
    ) -> str:
        captured["update_payload"] = update_payload
        captured["update_id"] = update_id
        return "processed"

    monkeypatch.setattr(telegram_updates, "process_update_async", fake_process_update_async)

    result = telegram_updates.process_telegram_update(update_payload={"update_id": 777})
    assert result == "processed"
    assert captured["update_id"] == 777


def test_process_telegram_update_prefers_explicit_update_id(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_process_update_async(
        update_payload: dict[str, object],
        *,
        update_id: int,
    ) -> str:
        captured["update_id"] = update_id
        return "processed"

    monkeypatch.setattr(telegram_updates, "process_update_async", fake_process_update_async)

    result = telegram_updates.process_telegram_update(
        update_payload={"update_id": 777},
        update_id=888,
    )
    assert result == "processed"
    assert captured["update_id"] == 888
