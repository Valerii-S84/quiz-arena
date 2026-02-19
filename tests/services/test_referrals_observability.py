from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.referrals_observability import (
    ReferralsAlertThresholds,
    ReferralsDashboardSnapshot,
    evaluate_referrals_alert_state,
    get_referrals_alert_thresholds,
)


def _snapshot(
    *,
    started: int,
    fraud_rate: float,
    rejected_total: int,
    top_referrers: list[dict[str, object]],
) -> ReferralsDashboardSnapshot:
    return ReferralsDashboardSnapshot(
        generated_at=datetime.now(timezone.utc),
        window_hours=24,
        referrals_started_total=started,
        status_counts={},
        qualified_like_total=0,
        rewarded_total=0,
        rejected_fraud_total=rejected_total,
        canceled_total=0,
        qualification_rate=0.0,
        reward_rate=0.0,
        fraud_rejected_rate=fraud_rate,
        top_referrers=top_referrers,
        recent_fraud_cases=[],
    )


def test_get_referrals_alert_thresholds_reads_settings_values() -> None:
    thresholds = get_referrals_alert_thresholds(
        SimpleNamespace(
            referrals_alert_min_started=30,
            referrals_alert_max_fraud_rejected_rate=0.4,
            referrals_alert_max_rejected_fraud_total=12,
            referrals_alert_max_referrer_rejected_fraud=4,
        )
    )

    assert thresholds == ReferralsAlertThresholds(
        min_started=30,
        max_fraud_rejected_rate=0.4,
        max_rejected_fraud_total=12,
        max_referrer_rejected_fraud=4,
    )


def test_evaluate_referrals_alert_state_requires_min_started() -> None:
    thresholds = ReferralsAlertThresholds(
        min_started=20,
        max_fraud_rejected_rate=0.25,
        max_rejected_fraud_total=10,
        max_referrer_rejected_fraud=3,
    )
    state = evaluate_referrals_alert_state(
        snapshot=_snapshot(
            started=19,
            fraud_rate=1.0,
            rejected_total=100,
            top_referrers=[{"rejected_fraud_total": 99}],
        ),
        thresholds=thresholds,
    )

    assert state.thresholds_applied is False
    assert state.fraud_spike_detected is False


def test_evaluate_referrals_alert_state_detects_fraud_spike_conditions() -> None:
    thresholds = ReferralsAlertThresholds(
        min_started=10,
        max_fraud_rejected_rate=0.2,
        max_rejected_fraud_total=4,
        max_referrer_rejected_fraud=2,
    )
    state = evaluate_referrals_alert_state(
        snapshot=_snapshot(
            started=100,
            fraud_rate=0.25,
            rejected_total=5,
            top_referrers=[{"rejected_fraud_total": 2}],
        ),
        thresholds=thresholds,
    )

    assert state.thresholds_applied is True
    assert state.fraud_spike_detected is True
    assert state.fraud_rate_above_threshold is True
    assert state.rejected_fraud_total_above_threshold is True
    assert state.referrer_spike_detected is True
