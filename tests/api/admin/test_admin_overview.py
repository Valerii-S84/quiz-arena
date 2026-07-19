from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.api.routes.admin import (
    overview,
    overview_activity_metrics,
    overview_language,
    overview_metrics,
    overview_queries,
    overview_streak_metrics,
)
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import AsyncSessionStub
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult


class _SessionWithExec(AsyncSessionStub):
    def __init__(self, *results) -> None:
        self._results = list(results)

    async def execute(self, stmt):
        del stmt
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_overview_metrics_helpers_compute_expected_values() -> None:
    assert overview_metrics.build_kpi(current=10.0, previous=5.0) == {
        "current": 10.0,
        "previous": 5.0,
        "delta_pct": 100.0,
    }
    assert overview_metrics.build_kpi(current=0.0, previous=0.0)["delta_pct"] == 0.0

    session = _SessionWithExec(
        _ScalarResult(11),
        _ScalarResult(7),
        _ScalarResult(3),
        _ScalarResult(99),
        _ScalarResult(5),
        _ScalarResult(2),
    )
    now_utc = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

    assert (
        await overview_activity_metrics.count_distinct_users(
            session,
            from_utc=now_utc,
            to_utc=now_utc,
        )
        == 11
    )
    assert (
        await overview_metrics.count_purchase_users(session, from_utc=now_utc, to_utc=now_utc) == 7
    )
    assert (
        await overview_metrics.count_first_purchase_users(session, from_utc=now_utc, to_utc=now_utc)
        == 3
    )
    assert await overview_metrics.sum_revenue_stars(session, from_utc=now_utc, to_utc=now_utc) == 99
    assert (
        await overview_metrics.count_distinct_event_users(
            session,
            event_type="bot_start_pressed",
            from_utc=now_utc,
            to_utc=now_utc,
        )
        == 5
    )
    assert (
        await overview_streak_metrics.count_users_reaching_streak_threshold(
            session,
            from_utc=now_utc,
            to_utc=now_utc,
            threshold=3,
        )
        == 2
    )


@pytest.mark.asyncio
async def test_retention_day_rate_handles_eligible_users_and_empty_cohorts() -> None:
    now_utc = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    created_at = datetime(2026, 3, 3, 9, 0, tzinfo=UTC)
    session = _SessionWithExec(
        _RowsResult([(101, created_at), (202, created_at)]),
        _RowsResult([(101, date(2026, 3, 4)), (202, date(2026, 3, 5))]),
    )
    rate = await overview_activity_metrics.retention_day_rate(
        session,
        from_utc=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
        to_utc=now_utc,
        day_offset=1,
    )
    assert rate == 50.0

    assert (
        await overview_activity_metrics.retention_day_rate(
            _SessionWithExec(_RowsResult([])),
            from_utc=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
            to_utc=now_utc,
            day_offset=7,
        )
        == 0.0
    )


@pytest.mark.asyncio
async def test_retention_day_rate_returns_zero_when_target_by_user_becomes_empty() -> None:
    session = _SessionWithExec(
        _RowsResult([(101, datetime(2026, 3, 9, 9, 0, tzinfo=UTC))]),
    )

    rate = await overview_activity_metrics.retention_day_rate(
        session,
        from_utc=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
        to_utc=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
        day_offset=30,
    )

    assert rate == 0.0
    assert session._results == []


@pytest.mark.asyncio
async def test_retention_day_rate_ignores_event_rows_with_missing_user_id() -> None:
    session = _SessionWithExec(
        _RowsResult([(101, datetime(2026, 3, 3, 9, 0, tzinfo=UTC))]),
        _RowsResult([(None, date(2026, 3, 4))]),
    )

    rate = await overview_activity_metrics.retention_day_rate(
        session,
        from_utc=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
        to_utc=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
        day_offset=1,
    )

    assert rate == 0.0


@pytest.mark.skip(
    reason="line 140 is unreachable: after `if not target_by_user: return 0.0`, `base = len(target_by_user)` is always > 0"
)
def test_retention_day_rate_base_guard_is_unreachable() -> None:
    pass


@pytest.mark.asyncio
async def test_fetch_user_language_distribution_normalizes_and_orders_language_codes() -> None:
    session = RecordingSession(_RowsResult([("de", 4), ("unknown", 2), ("en", 1)]))

    distribution = await overview_language.fetch_user_language_distribution(session)

    assert distribution == [
        {"language": "de", "users": 4},
        {"language": "unknown", "users": 2},
        {"language": "en", "users": 1},
    ]
    sql = compile_statement(session.statement)
    assert "coalesce(nullif(lower(trim(users.language_code)), ''), 'unknown')" in sql
    assert "ORDER BY count(users.id) DESC" in sql


@pytest.mark.asyncio
async def test_build_overview_payload_builds_kpis_and_alerts() -> None:
    session = _SessionWithExec(
        _ScalarResult(100),
        _ScalarResult(80),
        _ScalarResult(500),
        _ScalarResult(480),
        _ScalarResult(1000),
        _ScalarResult(900),
        _ScalarResult(20),
        _ScalarResult(10),
        _RowsResult([]),
        _RowsResult([]),
        _RowsResult([]),
        _RowsResult([]),
        _ScalarResult(200),
        _ScalarResult(100),
        _ScalarResult(7),
        _ScalarResult(4),
        _ScalarResult(20),
        _ScalarResult(10),
        _ScalarResult(5),
        _ScalarResult(5),
        _ScalarResult(3),
        _ScalarResult(5),
        _ScalarResult(10),
        _ScalarResult(7),
        _RowsResult([]),
        _RowsResult([]),
        _RowsResult([]),
        _RowsResult([(10, 2), (11, 3)]),
        _RowsResult([]),
        _RowsResult([("de", 2), ("en", 1)]),
        _ScalarResult(10),
        _ScalarResult(5),
        _ScalarResult(5),
        _ScalarResult(5),
        _ScalarResult(4),
        _ScalarResult(2),
        _ScalarResult(3),
        _ScalarResult(1),
        _ScalarResult(2),
        _ScalarResult(1),
        _ScalarResult(3),
        _ScalarResult(30),
    )
    now_utc = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    payload = overview.OverviewResponse.model_validate(
        await overview_queries.build_overview_payload(session, now_utc=now_utc, days=7)
    )

    assert payload.period == "7d"
    assert payload.kpis["dau"].current == 100.0
    assert payload.kpis["start_users"].current == 20.0
    assert payload.kpis["conversion_start_to_quiz"].current == 35.0
    assert payload.kpis["revenue_eur"].current == float(
        Decimal(200) * overview_metrics.STAR_TO_EUR_RATE
    )
    assert payload.feature_usage["duel_created_users"].current == 10.0
    assert payload.hourly_activity_series[10] == {"hour": 10, "active_users": 2}
    assert payload.hourly_activity_series[11] == {"hour": 11, "active_users": 3}
    assert payload.hourly_activity_series[12] == {"hour": 12, "active_users": 0}
    assert payload.user_language_distribution[0].language == "de"
    assert payload.user_language_distribution[0].users == 2
    assert payload.funnel[1] == {"step": "First Quiz", "value": 7}
    assert payload.funnel[2] == {"step": "Streak 3+", "value": 7}
    assert payload.funnel[3] == {"step": "Purchase", "value": 3}
    assert [str(item["type"]) for item in payload.alerts] == [
        "webhook_errors",
        "conversion_drop",
        "suspicious_activity",
    ]
