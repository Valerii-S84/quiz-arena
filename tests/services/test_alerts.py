from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import alerts


@pytest.mark.asyncio
async def test_send_ops_alert_returns_false_when_webhook_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(alerts, "get_settings", lambda: SimpleNamespace(ops_alert_webhook_url=""))
    sent = await alerts.send_ops_alert(event="test_event", payload={"k": "v"})
    assert sent is False


@pytest.mark.asyncio
async def test_send_ops_alert_posts_to_webhook(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

    class _Client:
        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
            return None

        async def post(self, url: str, json: dict[str, object]) -> _Response:
            captured["url"] = url
            captured["json"] = json
            return _Response()

    monkeypatch.setattr(
        alerts,
        "get_settings",
        lambda: SimpleNamespace(ops_alert_webhook_url="https://ops.example.local/hook"),
    )
    monkeypatch.setattr(alerts.httpx, "AsyncClient", lambda timeout: _Client())

    sent = await alerts.send_ops_alert(event="promo_campaign_auto_paused", payload={"paused_campaigns": 2})
    assert sent is True
    assert captured["url"] == "https://ops.example.local/hook"
    assert isinstance(captured["json"], dict)
    assert captured["json"]["event"] == "promo_campaign_auto_paused"
