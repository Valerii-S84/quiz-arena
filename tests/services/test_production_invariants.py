from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.production_invariants import (
    InvariantResult,
    build_invariant_checks,
    exit_code_for,
    read_only_sql_texts,
    record_alerts_for_results,
    render_json,
    render_text,
)
from app.workers.task_heartbeat import CriticalTaskHeartbeat

NOW_UTC = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def test_production_invariant_checks_include_required_p1_surfaces() -> None:
    names = {
        check.name
        for check in build_invariant_checks(
            NOW_UTC,
            heartbeat_registry=(
                CriticalTaskHeartbeat(
                    task_name="task",
                    schedule_key="schedule",
                    stale_after_seconds=120,
                ),
            ),
        )
    }

    assert {
        "paid_without_entitlement",
        "paid_uncredited_age_minutes",
        "paid_without_charge_id",
        "reconciliation_diff_nonzero",
        "daily_cup_expected_delivery_zero_outcomes",
        "tournament_round_expected_delivery_zero_outcomes",
        "private_tournament_round_delivery_gap",
        "telegram_delivery_failure_rate",
        "telegram_blocked_users_count",
        "worker_task_heartbeat_stale",
        "queue_oldest_message_age_seconds",
        "streak_update_stale",
        "global_best_streak_source_inconsistent",
        "analytics_daily_stale",
        "scheduled_offer_zero_delivery",
    }.issubset(names)


def test_production_invariant_sql_is_read_only() -> None:
    forbidden = re.compile(
        r"\b(insert|update|delete|merge|alter|drop|create|truncate|grant|revoke)\b",
        re.IGNORECASE,
    )

    assert read_only_sql_texts()
    for sql in read_only_sql_texts():
        assert forbidden.search(sql) is None


def test_scheduled_offer_check_uses_delivery_attempt_expectation_only() -> None:
    check = next(
        check
        for check in build_invariant_checks(NOW_UTC)
        if check.name == "scheduled_offer_zero_delivery"
    )

    assert "telegram_delivery_attempts" in check.sql
    assert "scheduled_offer_delivery" in check.sql
    assert "status = 'PENDING'" in check.sql
    assert "offers_impressions" not in check.sql
    assert "scheduled_offer_pending_cutoff" in check.params


def test_production_invariant_exit_code_blocks_only_p0_p1_failures() -> None:
    p2_only = [
        _result(name="analytics_daily_stale", status="FAIL", severity="P2", count=1),
    ]
    p1_failure = [
        _result(name="paid_without_entitlement", status="FAIL", severity="P1", count=1),
    ]

    assert exit_code_for(p2_only) == 0
    assert exit_code_for(p1_failure) == 1


def test_production_invariant_renderers_are_safe_and_stable() -> None:
    result = _result(name="telegram_blocked_users_count", status="FAIL", severity="P2", count=3)

    text = render_text([result])
    payload = render_json([result])

    assert "telegram_blocked_users_count" in text
    assert "telegram_user_id" not in text
    assert '"safe_context"' in payload
    assert '"count": 3' in payload


async def test_record_alerts_for_results_dedupes_and_resolves(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def _record_open(_session, **kwargs) -> None:
        calls.append(("open", kwargs))

    async def _mark_resolved(_session, **kwargs) -> int:
        calls.append(("resolved", kwargs))
        return 1

    from app.services import production_invariants

    monkeypatch.setattr(
        production_invariants.ProductionInvariantAlertsRepo,
        "record_open",
        _record_open,
    )
    monkeypatch.setattr(
        production_invariants.ProductionInvariantAlertsRepo,
        "mark_resolved",
        _mark_resolved,
    )

    summary = await record_alerts_for_results(
        cast(AsyncSession, object()),
        results=[
            _result(name="paid_without_entitlement", status="FAIL", severity="P1", count=2),
            _result(name="analytics_daily_stale", status="OK", severity="P2", count=0),
        ],
        seen_at=NOW_UTC,
    )

    assert summary == {"opened_or_updated": 1, "resolved": 1}
    assert calls[0][0] == "open"
    assert calls[0][1]["alert_type"] == "paid_without_entitlement"
    assert calls[1][0] == "resolved"


def _result(*, name: str, status: str, severity: str, count: int) -> InvariantResult:
    return InvariantResult(
        name=name,
        status=status,
        severity=severity,
        count=count,
        description=f"{name} description",
        correlation_key=name,
        safe_context={"check_name": name, "count": count},
    )
