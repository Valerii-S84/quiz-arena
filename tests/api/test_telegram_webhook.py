from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import telegram_webhook
from app.main import app


class StubTask:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def delay(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_webhook_enqueues_update_when_secret_is_valid(monkeypatch) -> None:
    stub_task = StubTask()
    monkeypatch.setattr(
        telegram_webhook,
        "get_settings",
        lambda: SimpleNamespace(telegram_webhook_secret="secret-token"),
    )
    monkeypatch.setattr(telegram_webhook, "process_telegram_update", stub_task)

    client = TestClient(app)
    response = client.post(
        "/webhook/telegram",
        json={"update_id": 12345, "message": {"message_id": 1}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "queued"}
    assert len(stub_task.calls) == 1
    assert stub_task.calls[0]["update_id"] == 12345


def test_webhook_ignores_invalid_secret(monkeypatch) -> None:
    stub_task = StubTask()
    monkeypatch.setattr(
        telegram_webhook,
        "get_settings",
        lambda: SimpleNamespace(telegram_webhook_secret="secret-token"),
    )
    monkeypatch.setattr(telegram_webhook, "process_telegram_update", stub_task)

    client = TestClient(app)
    response = client.post(
        "/webhook/telegram",
        json={"update_id": 12345},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert stub_task.calls == []


def test_webhook_ignores_payload_without_update_id(monkeypatch) -> None:
    stub_task = StubTask()
    monkeypatch.setattr(
        telegram_webhook,
        "get_settings",
        lambda: SimpleNamespace(telegram_webhook_secret="secret-token"),
    )
    monkeypatch.setattr(telegram_webhook, "process_telegram_update", stub_task)

    client = TestClient(app)
    response = client.post(
        "/webhook/telegram",
        json={"message": {"message_id": 1}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert stub_task.calls == []


def test_webhook_ignores_invalid_json(monkeypatch) -> None:
    stub_task = StubTask()
    monkeypatch.setattr(
        telegram_webhook,
        "get_settings",
        lambda: SimpleNamespace(telegram_webhook_secret="secret-token"),
    )
    monkeypatch.setattr(telegram_webhook, "process_telegram_update", stub_task)

    client = TestClient(app)
    response = client.post(
        "/webhook/telegram",
        content='{"update_id": 123',
        headers={
            "Content-Type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": "secret-token",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert stub_task.calls == []
