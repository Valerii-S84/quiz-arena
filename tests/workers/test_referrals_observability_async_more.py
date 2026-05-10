from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from app.workers.tasks import referrals_observability
from tests.workers.payments_reliability_async_support import SessionLocalStub


def test_referrals_fraud_alerts_async_sends_alert_when_degraded(
    monkeypatch,
) -> None:
    alerts: list[dict[str, object]] = []
    snapshot = SimpleNamespace(
        generated_at=datetime(2026, 5, 10, 12, 0, tzinfo=UTC),
        window_hours=12,
        referrals_started_total=30,
        qualified_like_total=10,
        rewarded_total=5,
        rejected_fraud_total=8,
        canceled_total=1,
        qualification_rate=0.33,
        reward_rate=0.16,
        fraud_rejected_rate=0.26,
        status_counts={"REJECTED_FRAUD": 8},
        top_referrers=[{"user_id": 1, "rejected": 4}],
        recent_fraud_cases=[{"referral_id": 99}],
    )
    thresholds = SimpleNamespace(
        min_started=10,
        max_fraud_rejected_rate=0.1,
        max_rejected_fraud_total=3,
        max_referrer_rejected_fraud=2,
    )
    alert_state = SimpleNamespace(
        thresholds_applied=True,
        fraud_spike_detected=True,
        fraud_rate_above_threshold=True,
        rejected_fraud_total_above_threshold=True,
        referrer_spike_detected=True,
    )

    monkeypatch.setattr(
        referrals_observability,
        "get_settings",
        lambda: SimpleNamespace(referrals_alert_window_hours=500),
    )
    monkeypatch.setattr(referrals_observability, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        referrals_observability,
        "get_referrals_alert_thresholds",
        lambda _settings: thresholds,
    )
    monkeypatch.setattr(
        referrals_observability,
        "build_referrals_dashboard_snapshot",
        _async_return(snapshot),
    )
    monkeypatch.setattr(
        referrals_observability,
        "evaluate_referrals_alert_state",
        lambda **_kwargs: alert_state,
    )
    monkeypatch.setattr(referrals_observability, "send_ops_alert", _append_kwargs(alerts))

    result = asyncio.run(referrals_observability.run_referrals_fraud_alerts_async())

    assert result["window_hours"] == 12
    alerts_result = cast(dict[str, Any], result["alerts"])
    assert alerts_result["fraud_spike_detected"] is True
    assert alerts[0]["event"] == "referral_fraud_spike_detected"


def test_referrals_window_clamp_bounds() -> None:
    assert referrals_observability._clamp_window_hours(0) == 1
    assert referrals_observability._clamp_window_hours(500) == 168


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _append_kwargs(target: list[dict[str, object]]):
    async def _inner(**kwargs) -> None:
        target.append(kwargs)

    return _inner
