from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.offers_observability import (
    OfferAlertThresholds,
    OfferFunnelSnapshot,
    evaluate_offer_alert_state,
    get_offer_alert_thresholds,
)


def _snapshot(
    *,
    impressions_total: int,
    conversion_rate: float,
    dismiss_rate: float,
    impressions_per_user: float,
) -> OfferFunnelSnapshot:
    return OfferFunnelSnapshot(
        generated_at=datetime.now(timezone.utc),
        window_hours=24,
        impressions_total=impressions_total,
        unique_users=10,
        clicks_total=5,
        dismissals_total=2,
        conversions_total=2,
        click_through_rate=0.5,
        conversion_rate=conversion_rate,
        dismiss_rate=dismiss_rate,
        impressions_per_user=impressions_per_user,
        top_offer_codes={},
    )


def test_get_offer_alert_thresholds_reads_settings_values() -> None:
    thresholds = get_offer_alert_thresholds(
        SimpleNamespace(
            offers_alert_min_impressions=25,
            offers_alert_min_conversion_rate=0.07,
            offers_alert_max_dismiss_rate=0.55,
            offers_alert_max_impressions_per_user=3.5,
        )
    )

    assert thresholds == OfferAlertThresholds(
        min_impressions=25,
        min_conversion_rate=0.07,
        max_dismiss_rate=0.55,
        max_impressions_per_user=3.5,
    )


def test_evaluate_offer_alert_state_is_not_applied_below_min_impressions() -> None:
    thresholds = OfferAlertThresholds(
        min_impressions=50,
        min_conversion_rate=0.05,
        max_dismiss_rate=0.6,
        max_impressions_per_user=4.0,
    )
    state = evaluate_offer_alert_state(
        snapshot=_snapshot(
            impressions_total=49,
            conversion_rate=0.0,
            dismiss_rate=1.0,
            impressions_per_user=10.0,
        ),
        thresholds=thresholds,
    )

    assert state.thresholds_applied is False
    assert state.conversion_drop_detected is False
    assert state.spam_anomaly_detected is False


def test_evaluate_offer_alert_state_detects_conversion_drop_and_spam() -> None:
    thresholds = OfferAlertThresholds(
        min_impressions=10,
        min_conversion_rate=0.2,
        max_dismiss_rate=0.4,
        max_impressions_per_user=2.0,
    )
    state = evaluate_offer_alert_state(
        snapshot=_snapshot(
            impressions_total=100,
            conversion_rate=0.1,
            dismiss_rate=0.45,
            impressions_per_user=2.2,
        ),
        thresholds=thresholds,
    )

    assert state.thresholds_applied is True
    assert state.conversion_drop_detected is True
    assert state.spam_anomaly_detected is True
    assert state.conversion_rate_below_threshold is True
    assert state.dismiss_rate_above_threshold is True
    assert state.impressions_per_user_above_threshold is True
