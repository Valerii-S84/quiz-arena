from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"
VALID_CHANNELS = {"generic", "slack", "pagerduty"}
VALID_SEVERITIES = {"critical", "error", "warning", "info"}
SEVERITY_COLOR = {
    "critical": "#B42318",
    "error": "#F04438",
    "warning": "#F79009",
    "info": "#1570EF",
}


@dataclass(frozen=True)
class AlertRoute:
    channels: tuple[str, ...]
    severity: str
    escalation_tier: str


@dataclass(frozen=True)
class AlertTarget:
    channel: str
    url: str


DEFAULT_ALERT_ROUTE = AlertRoute(
    channels=("generic",),
    severity="warning",
    escalation_tier="ops_l3",
)
EVENT_ALERT_ROUTES = {
    "promo_campaign_auto_paused": AlertRoute(
        channels=("slack", "generic"),
        severity="warning",
        escalation_tier="ops_l2",
    ),
    "payments_reconciliation_diff_detected": AlertRoute(
        channels=("pagerduty", "slack", "generic"),
        severity="critical",
        escalation_tier="ops_l1",
    ),
    "payments_recovery_review_required": AlertRoute(
        channels=("pagerduty", "slack", "generic"),
        severity="error",
        escalation_tier="ops_l1",
    ),
    "offers_conversion_drop_detected": AlertRoute(
        channels=("slack", "generic"),
        severity="warning",
        escalation_tier="ops_l2",
    ),
    "offers_spam_anomaly_detected": AlertRoute(
        channels=("slack", "generic"),
        severity="warning",
        escalation_tier="ops_l2",
    ),
    "referral_fraud_spike_detected": AlertRoute(
        channels=("slack", "generic"),
        severity="warning",
        escalation_tier="ops_l2",
    ),
    "referral_reward_milestone_available": AlertRoute(
        channels=("slack", "generic"),
        severity="info",
        escalation_tier="ops_l3",
    ),
    "referral_reward_granted": AlertRoute(
        channels=("slack", "generic"),
        severity="info",
        escalation_tier="ops_l3",
    ),
}
