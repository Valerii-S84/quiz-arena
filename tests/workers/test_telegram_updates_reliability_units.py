from __future__ import annotations

import asyncio

from app.workers.tasks import telegram_updates_reliability as reliability
from tests.workers.payments_reliability_async_support import SessionLocalStub


def test_retry_backoff_clamps_inputs_and_applies_jitter(monkeypatch) -> None:
    monkeypatch.setattr(reliability.random, "randint", lambda low, high: high)

    assert reliability.retry_backoff_seconds(next_retry_attempt=0, backoff_max_seconds=0) == 1
    assert reliability.retry_backoff_seconds(next_retry_attempt=3, backoff_max_seconds=10) == 5
    assert reliability.retry_backoff_seconds(next_retry_attempt=20, backoff_max_seconds=10) == 10


def test_emit_reliability_event_writes_outbox_event(monkeypatch) -> None:
    created: list[dict[str, object]] = []

    async def _create(_session, **kwargs) -> None:
        created.append(kwargs)

    monkeypatch.setattr(reliability, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(reliability.OutboxEventsRepo, "create", _create)

    asyncio.run(
        reliability.emit_reliability_event(
            event_type="retry",
            payload={"update_id": 100},
        )
    )

    assert created == [
        {
            "event_type": "retry",
            "payload": {"update_id": 100},
            "status": "SENT",
        }
    ]


def test_emit_reliability_event_logs_write_failure(monkeypatch) -> None:
    logs: list[dict[str, object]] = []

    async def _create(_session, **_kwargs) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(reliability, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(reliability.OutboxEventsRepo, "create", _create)
    monkeypatch.setattr(
        reliability.logger,
        "exception",
        lambda event, **kwargs: logs.append({"event": event, **kwargs}),
    )

    asyncio.run(reliability.emit_reliability_event(event_type="retry", payload={}))

    assert logs == [
        {
            "event": "telegram_update_reliability_event_write_failed",
            "event_type": "retry",
            "payload": {},
        }
    ]
