from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import telegram_webhook
from app.main import app


class StubTask:
    def __init__(self, order: list[str] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._order = order

    def delay(self, **kwargs: object) -> None:
        if self._order is not None:
            self._order.append("enqueue")
        self.calls.append(kwargs)


class LoopBoundStubTask:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def delay(self, **kwargs: object) -> None:
        asyncio.get_running_loop()
        self.calls.append(kwargs)


class FailingStubTask:
    def delay(self, **kwargs: object) -> None:
        raise RuntimeError("broker_unavailable")


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _SessionLocal:
    def begin(self) -> _SessionContext:
        return _SessionContext()


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        telegram_webhook_secret="secret-token",
        telegram_webhook_enqueue_timeout_ms=250,
    )


def test_webhook_enqueues_update_when_secret_is_valid(monkeypatch) -> None:
    stub_task = StubTask()
    monkeypatch.setattr(telegram_webhook, "get_settings", _settings)
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


def test_webhook_enqueues_with_loop_bound_task_fallback(monkeypatch) -> None:
    stub_task = LoopBoundStubTask()
    monkeypatch.setattr(telegram_webhook, "get_settings", _settings)
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


def test_webhook_returns_ignored_when_enqueue_fails(monkeypatch) -> None:
    stub_task = FailingStubTask()
    monkeypatch.setattr(telegram_webhook, "get_settings", _settings)
    monkeypatch.setattr(telegram_webhook, "process_telegram_update", stub_task)

    client = TestClient(app)
    response = client.post(
        "/webhook/telegram",
        json={"update_id": 12345, "message": {"message_id": 1}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
    )

    assert response.status_code == 503
    assert response.json() == {"status": "retry"}


def test_webhook_ignores_invalid_secret(monkeypatch) -> None:
    stub_task = StubTask()
    monkeypatch.setattr(telegram_webhook, "get_settings", _settings)
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
    monkeypatch.setattr(telegram_webhook, "get_settings", _settings)
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
    monkeypatch.setattr(telegram_webhook, "get_settings", _settings)
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


def test_payment_update_evidence_is_stored_before_enqueue(monkeypatch) -> None:
    order: list[str] = []
    stub_task = StubTask(order)
    stored: list[dict[str, object]] = []

    async def _create_once(_session, **kwargs):
        order.append("store")
        stored.append(kwargs)
        return object(), True

    monkeypatch.setattr(telegram_webhook, "get_settings", _settings)
    monkeypatch.setattr(telegram_webhook, "process_telegram_update", stub_task)
    monkeypatch.setattr(telegram_webhook, "SessionLocal", _SessionLocal())
    monkeypatch.setattr(
        telegram_webhook.OutboxEventsRepo,
        "create_once_by_payload_key",
        _create_once,
    )

    client = TestClient(app)
    response = client.post(
        "/webhook/telegram",
        json={
            "update_id": 777,
            "message": {
                "message_id": 1,
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 29,
                    "invoice_payload": "invoice-1",
                },
            },
        },
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
    )

    assert response.status_code == 200
    assert order == ["store", "enqueue"]
    assert stub_task.calls[0]["update_id"] == 777
    assert stored[0]["event_type"] == "telegram_payment_update_received"
    assert stored[0]["payload_key"] == "payment_update_key"
    assert stored[0]["status"] == "PENDING"
    payload = stored[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["payment_update_kind"] == "message.successful_payment"
    assert payload["payment_update_key"] == "777:message.successful_payment"
    raw_update = payload["raw_update"]
    assert isinstance(raw_update, dict)
    assert raw_update["update_id"] == 777


def test_payment_update_evidence_duplicate_still_enqueues_once(monkeypatch) -> None:
    stub_task = StubTask()
    seen: set[str] = set()
    created_count = 0

    async def _create_once(_session, *, payload: dict[str, object], **_kwargs):
        nonlocal created_count
        payment_update_key = str(payload["payment_update_key"])
        if payment_update_key in seen:
            return object(), False
        seen.add(payment_update_key)
        created_count += 1
        return object(), True

    monkeypatch.setattr(telegram_webhook, "get_settings", _settings)
    monkeypatch.setattr(telegram_webhook, "process_telegram_update", stub_task)
    monkeypatch.setattr(telegram_webhook, "SessionLocal", _SessionLocal())
    monkeypatch.setattr(
        telegram_webhook.OutboxEventsRepo,
        "create_once_by_payload_key",
        _create_once,
    )

    client = TestClient(app)
    payload = {"update_id": 778, "pre_checkout_query": {"id": "pre-1"}}
    for _ in range(2):
        response = client.post(
            "/webhook/telegram",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
        )
        assert response.status_code == 200

    assert created_count == 1
    assert len(stub_task.calls) == 2


def test_payment_update_evidence_store_failure_returns_retry(monkeypatch) -> None:
    stub_task = StubTask()

    async def _fail_create_once(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(telegram_webhook, "get_settings", _settings)
    monkeypatch.setattr(telegram_webhook, "process_telegram_update", stub_task)
    monkeypatch.setattr(telegram_webhook, "SessionLocal", _SessionLocal())
    monkeypatch.setattr(
        telegram_webhook.OutboxEventsRepo,
        "create_once_by_payload_key",
        _fail_create_once,
    )

    client = TestClient(app)
    response = client.post(
        "/webhook/telegram",
        json={"update_id": 779, "pre_checkout_query": {"id": "pre-1"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
    )

    assert response.status_code == 503
    assert response.json() == {"status": "retry"}
    assert stub_task.calls == []


def test_non_payment_update_does_not_store_evidence(monkeypatch) -> None:
    stub_task = StubTask()

    async def _create_once(*_args, **_kwargs):
        raise AssertionError("non-payment update must not create payment evidence")

    monkeypatch.setattr(telegram_webhook, "get_settings", _settings)
    monkeypatch.setattr(telegram_webhook, "process_telegram_update", stub_task)
    monkeypatch.setattr(telegram_webhook, "SessionLocal", _SessionLocal())
    monkeypatch.setattr(
        telegram_webhook.OutboxEventsRepo,
        "create_once_by_payload_key",
        _create_once,
    )

    client = TestClient(app)
    response = client.post(
        "/webhook/telegram",
        json={"update_id": 780, "message": {"message_id": 1, "text": "/start"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
    )

    assert response.status_code == 200
    assert len(stub_task.calls) == 1
