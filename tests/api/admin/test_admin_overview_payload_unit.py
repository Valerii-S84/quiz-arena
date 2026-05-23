from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.api.routes.admin import overview_payload, overview_payload_conversion
from app.api.routes.admin.overview_payload_conversion import (
    ConversionSnapshot,
    build_conversion_kpis,
)
from app.api.routes.admin.overview_payload_kpis import RangeKpiSnapshot, build_windows
from tests.type_helpers import AsyncSessionStub

NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def test_build_windows_creates_adjacent_current_and_previous_ranges() -> None:
    windows = build_windows(now_utc=NOW, days=7)

    assert windows.current_end == NOW
    assert windows.current_start == NOW - timedelta(days=7)
    assert windows.previous_end == windows.current_start
    assert windows.previous_start == NOW - timedelta(days=14)


def test_conversion_kpis_return_zero_when_denominator_is_empty() -> None:
    snapshot = ConversionSnapshot(
        start_users_now=0,
        start_users_prev=10,
        first_quiz_users_now=5,
        first_quiz_users_prev=4,
        quiz_users_now=0,
        quiz_users_prev=20,
        purchase_users_now=3,
        purchase_users_prev=5,
        first_purchase_users_now=2,
    )

    kpis = build_conversion_kpis(snapshot)

    assert kpis["conversion_start_to_quiz"]["current"] == 0.0
    assert kpis["conversion_start_to_quiz"]["previous"] == 40.0
    assert kpis["conversion_quiz_to_purchase"]["current"] == 0.0
    assert kpis["conversion_quiz_to_purchase"]["previous"] == 25.0


@pytest.mark.asyncio
async def test_build_alerts_returns_only_triggered_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    session_stub = AsyncSessionStub()

    async def _fetch_alert_inputs(session, *, now_utc):
        assert session is session_stub
        assert now_utc == NOW
        return 2, 25

    monkeypatch.setattr(overview_payload, "fetch_alert_inputs", _fetch_alert_inputs)

    alerts = await overview_payload._build_alerts(
        session_stub,
        now_utc=NOW,
        quiz_to_purchase_now=79.9,
        quiz_to_purchase_prev=100.0,
    )
    assert [alert["type"] for alert in alerts] == [
        "webhook_errors",
        "conversion_drop",
        "suspicious_activity",
    ]


@pytest.mark.asyncio
async def test_load_conversion_snapshot_uses_windowed_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    session_stub = AsyncSessionStub()
    windows = build_windows(now_utc=NOW, days=7)

    async def _counter(name: str, value: int, session, *, from_utc, to_utc):
        assert session is session_stub
        assert (from_utc, to_utc) in {
            (windows.current_start, windows.current_end),
            (windows.previous_start, windows.previous_end),
        }
        calls.append(name)
        return value

    counters = {
        "count_first_quiz_users": ("first_quiz", 3),
        "count_quiz_users": ("quiz", 4),
        "count_purchase_users": ("purchase", 2),
        "count_first_purchase_users": ("first_purchase", 1),
    }
    for attr, (name, value) in counters.items():
        monkeypatch.setattr(
            overview_payload_conversion,
            attr,
            lambda *args, name=name, value=value, **kwargs: _counter(name, value, *args, **kwargs),
        )

    snapshot = await overview_payload_conversion.load_conversion_snapshot(
        session_stub,
        start_users_now=10,
        start_users_prev=5,
        windows=windows,
    )

    assert snapshot.start_users_now == 10
    assert snapshot.first_purchase_users_now == 1
    assert calls[-1] == "first_purchase"


@pytest.mark.asyncio
async def test_build_overview_payload_combines_empty_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_stub = AsyncSessionStub()

    async def _activity_kpis(session, *, now_utc, windows):
        assert session is session_stub
        assert now_utc == NOW
        assert windows.current_end == NOW
        return {"dau": {"current": 1.0, "previous": 0.0, "delta_pct": 100.0}}

    async def _range_kpis(session, *, windows):
        del session, windows
        return RangeKpiSnapshot(kpis={}, new_users_now=4, new_users_prev=2)

    async def _conversion_snapshot(session, *, start_users_now, start_users_prev, windows):
        del session, windows
        return ConversionSnapshot(
            start_users_now=start_users_now,
            start_users_prev=start_users_prev,
            first_quiz_users_now=2,
            first_quiz_users_prev=1,
            quiz_users_now=2,
            quiz_users_prev=1,
            purchase_users_now=1,
            purchase_users_prev=1,
            first_purchase_users_now=1,
        )

    async def _subscription_kpis(session, *, now_utc, previous_end):
        del session, now_utc, previous_end
        return {"active_subscriptions": {"current": 0.0, "previous": 0.0, "delta_pct": 0.0}}

    async def _count_streaks(session, **kwargs):
        del session, kwargs
        return 0

    async def _empty_list(session, **kwargs):
        del session, kwargs
        return []

    async def _feature_usage(session, **kwargs):
        del session, kwargs
        return {}

    async def _alerts(session, **kwargs):
        del session, kwargs
        return []

    monkeypatch.setattr(overview_payload, "build_activity_kpis", _activity_kpis)
    monkeypatch.setattr(overview_payload, "build_range_kpis", _range_kpis)
    monkeypatch.setattr(overview_payload, "load_conversion_snapshot", _conversion_snapshot)
    monkeypatch.setattr(overview_payload, "build_subscription_kpis", _subscription_kpis)
    monkeypatch.setattr(overview_payload, "count_users_reaching_streak_threshold", _count_streaks)
    monkeypatch.setattr(overview_payload, "fetch_revenue_series", _empty_list)
    monkeypatch.setattr(overview_payload, "fetch_users_series", _empty_list)
    monkeypatch.setattr(overview_payload, "fetch_hourly_activity_series", _empty_list)
    monkeypatch.setattr(overview_payload, "fetch_top_products", _empty_list)
    monkeypatch.setattr(overview_payload, "fetch_user_language_distribution", _empty_list)
    monkeypatch.setattr(overview_payload, "build_feature_usage_payload", _feature_usage)
    monkeypatch.setattr(overview_payload, "_build_alerts", _alerts)

    payload = await overview_payload.build_overview_payload(session_stub, now_utc=NOW, days=7)

    assert payload["period"] == "7d"
    assert payload["revenue_series"] == []
    assert payload["users_series"] == []
    assert payload["hourly_activity_series"] == []
    assert payload["top_products"] == []
    assert payload["user_language_distribution"] == []
    assert payload["user_age_distribution"] == []
    assert payload["user_gender_distribution"] == []
    assert payload["feature_usage"] == {}
    assert payload["alerts"] == []
    assert payload["funnel"] == [
        {"step": "Start", "value": 4},
        {"step": "First Quiz", "value": 2},
        {"step": "Streak 3+", "value": 0},
        {"step": "Purchase", "value": 1},
    ]
