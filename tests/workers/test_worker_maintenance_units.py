from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.workers.tasks import (
    offers_observability,
    payments_reliability_reconciliation,
    promo_maintenance,
)
from tests.workers.payments_reliability_async_support import SessionLocalStub

NOW_UTC = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_promo_maintenance_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    alerts: list[dict[str, object]] = []
    monkeypatch.setattr(promo_maintenance, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        promo_maintenance.PromoRepo,
        "expire_reserved_redemptions",
        _async_return(2),
    )
    monkeypatch.setattr(promo_maintenance.PromoRepo, "expire_active_codes", _async_return(3))
    monkeypatch.setattr(promo_maintenance.PromoRepo, "deplete_active_codes", _async_return(4))
    monkeypatch.setattr(
        promo_maintenance.PromoRepo,
        "get_abusive_code_hashes",
        _async_return(["hash-1", "hash-2"]),
    )
    monkeypatch.setattr(
        promo_maintenance.PromoRepo,
        "pause_active_codes_by_hashes",
        _async_return(2),
    )
    monkeypatch.setattr(promo_maintenance, "send_ops_alert", _append_kwargs(alerts))

    assert await promo_maintenance.run_promo_reservation_expiry_async() == {
        "expired_redemptions": 2
    }
    assert await promo_maintenance.run_promo_campaign_status_rollover_async() == {
        "expired_campaigns": 3,
        "depleted_campaigns": 4,
        "updated_campaigns": 7,
    }
    assert await promo_maintenance.run_promo_bruteforce_guard_async() == {
        "abusive_hashes": 2,
        "paused_campaigns": 2,
    }
    assert alerts[0]["event"] == "promo_campaign_auto_paused"


@pytest.mark.asyncio
async def test_payments_reconciliation_sends_alert_on_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    alerts: list[dict[str, object]] = []
    monkeypatch.setattr(payments_reliability_reconciliation, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        payments_reliability_reconciliation.PurchasesRepo,
        "count_paid_purchases",
        _async_return(3),
    )
    monkeypatch.setattr(
        payments_reliability_reconciliation.LedgerRepo,
        "count_distinct_purchase_credits",
        _async_return(2),
    )
    monkeypatch.setattr(
        payments_reliability_reconciliation.PurchasesRepo,
        "sum_paid_stars_amount",
        _async_return(100),
    )
    monkeypatch.setattr(
        payments_reliability_reconciliation.LedgerRepo,
        "sum_distinct_purchase_stars_for_credits",
        _async_return(90),
    )
    monkeypatch.setattr(
        payments_reliability_reconciliation.PurchasesRepo,
        "sum_paid_stars_amount_by_product",
        _async_return({}),
    )
    monkeypatch.setattr(
        payments_reliability_reconciliation.LedgerRepo,
        "sum_distinct_purchase_stars_for_credits_by_product",
        _async_return({}),
    )
    monkeypatch.setattr(
        payments_reliability_reconciliation.PurchasesRepo,
        "count_paid_uncredited_older_than",
        _async_return(1),
    )
    monkeypatch.setattr(
        payments_reliability_reconciliation.ReconciliationRunsRepo,
        "create",
        _async_return(None),
    )
    monkeypatch.setattr(
        payments_reliability_reconciliation, "send_ops_alert", _append_kwargs(alerts)
    )

    result = await payments_reliability_reconciliation.run_payments_reconciliation_async(
        stale_minutes=15
    )

    diff_count = result["diff_count"]
    assert isinstance(diff_count, int)
    assert diff_count > 0
    assert result["status"] == "DIFF"
    assert alerts[0]["event"] == "payments_reconciliation_diff_detected"


@pytest.mark.asyncio
async def test_offers_funnel_alerts_emits_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    alerts: list[dict[str, object]] = []
    snapshot = SimpleNamespace(
        generated_at=NOW_UTC,
        window_hours=24,
        impressions_total=100,
        unique_users=10,
        clicks_total=5,
        dismissals_total=90,
        conversions_total=1,
        click_through_rate=0.05,
        conversion_rate=0.01,
        dismiss_rate=0.9,
        impressions_per_user=10,
        top_offer_codes=["OFFER"],
    )
    thresholds = SimpleNamespace(
        min_impressions=10,
        min_conversion_rate=0.1,
        max_dismiss_rate=0.5,
        max_impressions_per_user=5,
    )
    alert_state = SimpleNamespace(
        thresholds_applied=True,
        conversion_drop_detected=True,
        spam_anomaly_detected=True,
        conversion_rate_below_threshold=True,
        dismiss_rate_above_threshold=True,
        impressions_per_user_above_threshold=True,
    )
    monkeypatch.setattr(
        offers_observability,
        "get_settings",
        lambda: SimpleNamespace(offers_alert_window_hours=1000),
    )
    monkeypatch.setattr(offers_observability, "SessionLocal", SessionLocalStub())
    monkeypatch.setattr(
        offers_observability, "get_offer_alert_thresholds", lambda _settings: thresholds
    )
    monkeypatch.setattr(
        offers_observability,
        "build_offer_funnel_snapshot",
        _async_return(snapshot),
    )
    monkeypatch.setattr(
        offers_observability,
        "evaluate_offer_alert_state",
        lambda **_kwargs: alert_state,
    )
    monkeypatch.setattr(offers_observability, "send_ops_alert", _append_kwargs(alerts))

    result = await offers_observability.run_offers_funnel_alerts_async()

    assert result["window_hours"] == 24
    assert len(alerts) == 2


def test_offer_window_clamp() -> None:
    assert offers_observability._clamp_window_hours(0) == 1
    assert offers_observability._clamp_window_hours(999) == 168


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _append_kwargs(target: list[dict[str, object]]):
    async def _inner(**kwargs) -> None:
        target.append(kwargs)

    return _inner
