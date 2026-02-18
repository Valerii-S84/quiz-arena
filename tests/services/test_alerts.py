from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services import alerts


class _Response:
    def raise_for_status(self) -> None:
        return None


class _Client:
    def __init__(self, calls: list[dict[str, Any]], *, fail_urls: set[str] | None = None) -> None:
        self._calls = calls
        self._fail_urls = fail_urls or set()

    async def __aenter__(self) -> "_Client":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None

    async def post(self, url: str, json: dict[str, object]) -> _Response:
        self._calls.append({"url": url, "json": json})
        if url in self._fail_urls:
            raise RuntimeError("delivery failed")
        return _Response()


def _settings(**overrides: object) -> SimpleNamespace:
    base = {
        "app_env": "test",
        "ops_alert_webhook_url": "",
        "ops_alert_slack_webhook_url": "",
        "ops_alert_pagerduty_events_url": "",
        "ops_alert_pagerduty_routing_key": "",
        "ops_alert_escalation_policy_json": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _patch_http_client(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[dict[str, Any]],
    *,
    fail_urls: set[str] | None = None,
) -> None:
    def factory(timeout: float) -> _Client:  # noqa: ARG001
        return _Client(calls, fail_urls=fail_urls)

    monkeypatch.setattr(alerts.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_send_ops_alert_returns_false_when_no_targets_configured(monkeypatch) -> None:
    monkeypatch.setattr(alerts, "get_settings", lambda: _settings())
    sent = await alerts.send_ops_alert(event="test_event", payload={"k": "v"})
    assert sent is False


@pytest.mark.asyncio
async def test_send_ops_alert_posts_to_generic_webhook(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        alerts,
        "get_settings",
        lambda: _settings(ops_alert_webhook_url="https://ops.example.local/hook"),
    )
    _patch_http_client(monkeypatch, calls)
    sent = await alerts.send_ops_alert(event="promo_campaign_auto_paused", payload={"paused_campaigns": 2})

    assert sent is True
    assert len(calls) == 1
    assert calls[0]["url"] == "https://ops.example.local/hook"
    body = calls[0]["json"]
    assert body["event"] == "promo_campaign_auto_paused"
    assert body["severity"] == "warning"
    assert body["escalation_tier"] == "ops_l2"


@pytest.mark.asyncio
async def test_send_ops_alert_routes_critical_event_to_pagerduty_and_slack(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        alerts,
        "get_settings",
        lambda: _settings(
            ops_alert_slack_webhook_url="https://slack.example.local/hook",
            ops_alert_pagerduty_routing_key="pd_key",
        ),
    )
    _patch_http_client(monkeypatch, calls)

    sent = await alerts.send_ops_alert(
        event="payments_reconciliation_diff_detected",
        payload={"diff_count": 3},
    )

    assert sent is True
    assert len(calls) == 2
    assert calls[0]["url"] == alerts.DEFAULT_PAGERDUTY_EVENTS_URL
    assert calls[0]["json"]["routing_key"] == "pd_key"
    assert calls[0]["json"]["payload"]["severity"] == "critical"
    assert calls[0]["json"]["payload"]["group"] == "ops_l1"
    assert calls[1]["url"] == "https://slack.example.local/hook"
    assert "CRITICAL" in calls[1]["json"]["text"]


@pytest.mark.asyncio
async def test_send_ops_alert_applies_policy_override(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        alerts,
        "get_settings",
        lambda: _settings(
            ops_alert_webhook_url="https://ops.example.local/hook",
            ops_alert_pagerduty_events_url="https://pagerduty.example.local/enqueue",
            ops_alert_pagerduty_routing_key="pd_key",
            ops_alert_escalation_policy_json=(
                '{"promo_campaign_auto_paused":{"channels":["pagerduty"],'
                '"severity":"critical","escalation_tier":"ops_override"}}'
            ),
        ),
    )
    _patch_http_client(monkeypatch, calls)

    sent = await alerts.send_ops_alert(event="promo_campaign_auto_paused", payload={"paused_campaigns": 1})

    assert sent is True
    assert len(calls) == 1
    assert calls[0]["url"] == "https://pagerduty.example.local/enqueue"
    assert calls[0]["json"]["payload"]["severity"] == "critical"
    assert calls[0]["json"]["payload"]["group"] == "ops_override"


@pytest.mark.asyncio
async def test_send_ops_alert_returns_true_when_one_provider_fails(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        alerts,
        "get_settings",
        lambda: _settings(
            ops_alert_webhook_url="https://ops.example.local/hook",
            ops_alert_slack_webhook_url="https://slack.example.local/hook",
        ),
    )
    _patch_http_client(monkeypatch, calls, fail_urls={"https://slack.example.local/hook"})

    sent = await alerts.send_ops_alert(event="promo_campaign_auto_paused", payload={"paused_campaigns": 5})

    assert sent is True
    assert len(calls) == 2
