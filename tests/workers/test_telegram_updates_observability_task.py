from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.workers.tasks import telegram_updates_observability


class _AsyncBeginContext:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        return None


def _session_local_with_sessions(*sessions: object) -> SimpleNamespace:
    remaining = list(sessions)

    def _begin() -> _AsyncBeginContext:
        return _AsyncBeginContext(remaining.pop(0))

    return SimpleNamespace(begin=_begin)


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


@pytest.mark.asyncio
async def test_reliability_alerts_async_returns_metrics_without_alert_when_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info_logs: list[dict[str, object]] = []
    alert_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        telegram_updates_observability,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_update_processing_ttl_seconds=300,
            telegram_updates_alert_window_minutes=15,
            telegram_updates_stuck_alert_min_minutes=10,
            telegram_updates_retry_spike_threshold=3,
            telegram_updates_failed_final_spike_threshold=2,
            telegram_updates_observability_top_stuck_limit=5,
        ),
    )
    monkeypatch.setattr(
        telegram_updates_observability,
        "SessionLocal",
        _session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(
        telegram_updates_observability.ProcessedUpdatesRepo,
        "count_processing_older_than_seconds",
        lambda *args, **kwargs: _async_return(0)(*args, **kwargs),
    )
    monkeypatch.setattr(
        telegram_updates_observability.ProcessedUpdatesRepo,
        "get_processing_age_max_seconds",
        lambda *args, **kwargs: _async_return(300)(*args, **kwargs),
    )
    monkeypatch.setattr(
        telegram_updates_observability.ProcessedUpdatesRepo,
        "list_oldest_processing",
        lambda *args, **kwargs: _async_return([])(*args, **kwargs),
    )
    monkeypatch.setattr(
        telegram_updates_observability.OutboxEventsRepo,
        "count_by_type_since",
        lambda *args, **kwargs: _async_return({})(*args, **kwargs),
    )
    monkeypatch.setattr(
        telegram_updates_observability,
        "send_ops_alert",
        _capture_async_calls(alert_calls),
    )
    monkeypatch.setattr(
        telegram_updates_observability.logger,
        "info",
        lambda event, **kwargs: info_logs.append({"event": event, **kwargs}),
    )

    result = await telegram_updates_observability.run_telegram_updates_reliability_alerts_async()

    assert result["processed_updates_processing_stuck_count"] == 0
    assert result["processed_updates_processing_age_max_seconds"] == 300
    assert result["alerts"] == {
        "stuck_detected": False,
        "max_age_exceeded": False,
        "retries_spike_detected": False,
        "failed_final_spike_detected": False,
    }
    assert result["oldest_processing"] == []
    assert alert_calls == []
    assert info_logs[0]["event"] == "telegram_updates_reliability_alerts_ok"


@pytest.mark.asyncio
async def test_reliability_alerts_async_sends_ops_alert_when_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warning_logs: list[dict[str, object]] = []
    alert_calls: list[dict[str, object]] = []
    oldest_processing = [{"update_id": 123, "age_seconds": 901}]

    monkeypatch.setattr(
        telegram_updates_observability,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_update_processing_ttl_seconds=300,
            telegram_updates_alert_window_minutes=15,
            telegram_updates_stuck_alert_min_minutes=10,
            telegram_updates_retry_spike_threshold=3,
            telegram_updates_failed_final_spike_threshold=1,
            telegram_updates_observability_top_stuck_limit=5,
        ),
    )
    monkeypatch.setattr(
        telegram_updates_observability,
        "SessionLocal",
        _session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(
        telegram_updates_observability.ProcessedUpdatesRepo,
        "count_processing_older_than_seconds",
        lambda *args, **kwargs: _async_return(2)(*args, **kwargs),
    )
    monkeypatch.setattr(
        telegram_updates_observability.ProcessedUpdatesRepo,
        "get_processing_age_max_seconds",
        lambda *args, **kwargs: _async_return(901)(*args, **kwargs),
    )
    monkeypatch.setattr(
        telegram_updates_observability.ProcessedUpdatesRepo,
        "list_oldest_processing",
        lambda *args, **kwargs: _async_return(oldest_processing)(*args, **kwargs),
    )
    monkeypatch.setattr(
        telegram_updates_observability.OutboxEventsRepo,
        "count_by_type_since",
        lambda *args, **kwargs: _async_return(
            {
                telegram_updates_observability.EVENT_TELEGRAM_UPDATE_RECLAIMED: 1,
                telegram_updates_observability.EVENT_TELEGRAM_UPDATE_RETRY_SCHEDULED: 4,
                telegram_updates_observability.EVENT_TELEGRAM_UPDATE_FAILED_FINAL: 2,
            }
        )(*args, **kwargs),
    )
    monkeypatch.setattr(
        telegram_updates_observability,
        "send_ops_alert",
        _capture_async_calls(alert_calls),
    )
    monkeypatch.setattr(
        telegram_updates_observability.logger,
        "warning",
        lambda event, **kwargs: warning_logs.append({"event": event, **kwargs}),
    )

    result = await telegram_updates_observability.run_telegram_updates_reliability_alerts_async()

    assert result["processed_updates_processing_stuck_count"] == 2
    assert result["telegram_updates_retries_total"] == 4
    assert result["telegram_updates_failed_final_total"] == 2
    assert result["alerts"] == {
        "stuck_detected": True,
        "max_age_exceeded": True,
        "retries_spike_detected": True,
        "failed_final_spike_detected": True,
    }
    assert alert_calls == [
        {
            "event": "telegram_updates_reliability_degraded",
            "payload": result,
        }
    ]
    assert warning_logs[0]["event"] == "telegram_updates_reliability_alerts_detected"


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


def _capture_async_calls(calls: list[dict[str, object]]):
    async def _inner(**kwargs):
        calls.append(kwargs)

    return _inner
