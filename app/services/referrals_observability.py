from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.referrals_repo import ReferralsRepo


def _safe_rate(*, numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


@dataclass(frozen=True, slots=True)
class ReferralsDashboardSnapshot:
    generated_at: datetime
    window_hours: int
    referrals_started_total: int
    status_counts: dict[str, int]
    qualified_like_total: int
    rewarded_total: int
    rejected_fraud_total: int
    canceled_total: int
    qualification_rate: float
    reward_rate: float
    fraud_rejected_rate: float
    top_referrers: list[dict[str, object]]
    recent_fraud_cases: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class ReferralsAlertThresholds:
    min_started: int
    max_fraud_rejected_rate: float
    max_rejected_fraud_total: int
    max_referrer_rejected_fraud: int


@dataclass(frozen=True, slots=True)
class ReferralsAlertState:
    thresholds_applied: bool
    fraud_spike_detected: bool
    fraud_rate_above_threshold: bool
    rejected_fraud_total_above_threshold: bool
    referrer_spike_detected: bool


def _clamp_non_negative_int(value: object, default: int) -> int:
    if not isinstance(value, int):
        return default
    return max(0, value)


def _clamp_rate(value: object, default: float) -> float:
    if not isinstance(value, (int, float)):
        return default
    return min(1.0, max(0.0, float(value)))


def get_referrals_alert_thresholds(settings: object) -> ReferralsAlertThresholds:
    return ReferralsAlertThresholds(
        min_started=_clamp_non_negative_int(
            getattr(settings, "referrals_alert_min_started", 20),
            20,
        ),
        max_fraud_rejected_rate=_clamp_rate(
            getattr(settings, "referrals_alert_max_fraud_rejected_rate", 0.25),
            0.25,
        ),
        max_rejected_fraud_total=_clamp_non_negative_int(
            getattr(settings, "referrals_alert_max_rejected_fraud_total", 10),
            10,
        ),
        max_referrer_rejected_fraud=_clamp_non_negative_int(
            getattr(settings, "referrals_alert_max_referrer_rejected_fraud", 3),
            3,
        ),
    )


def evaluate_referrals_alert_state(
    *,
    snapshot: ReferralsDashboardSnapshot,
    thresholds: ReferralsAlertThresholds,
) -> ReferralsAlertState:
    thresholds_applied = snapshot.referrals_started_total >= thresholds.min_started
    if not thresholds_applied:
        return ReferralsAlertState(
            thresholds_applied=False,
            fraud_spike_detected=False,
            fraud_rate_above_threshold=False,
            rejected_fraud_total_above_threshold=False,
            referrer_spike_detected=False,
        )

    fraud_rate_above_threshold = snapshot.fraud_rejected_rate > thresholds.max_fraud_rejected_rate
    rejected_fraud_total_above_threshold = snapshot.rejected_fraud_total > thresholds.max_rejected_fraud_total
    referrer_spike_detected = any(
        int(row.get("rejected_fraud_total", 0)) >= thresholds.max_referrer_rejected_fraud
        for row in snapshot.top_referrers
    )

    return ReferralsAlertState(
        thresholds_applied=True,
        fraud_spike_detected=(
            fraud_rate_above_threshold
            or rejected_fraud_total_above_threshold
            or referrer_spike_detected
        ),
        fraud_rate_above_threshold=fraud_rate_above_threshold,
        rejected_fraud_total_above_threshold=rejected_fraud_total_above_threshold,
        referrer_spike_detected=referrer_spike_detected,
    )


async def build_referrals_dashboard_snapshot(
    session: AsyncSession,
    *,
    now_utc: datetime,
    window_hours: int,
    top_referrers_limit: int = 20,
    recent_cases_limit: int = 50,
) -> ReferralsDashboardSnapshot:
    since_utc = now_utc - timedelta(hours=window_hours)
    started_total = await ReferralsRepo.count_started_since(session, since_utc=since_utc)
    status_counts = await ReferralsRepo.count_by_status_since(session, since_utc=since_utc)
    top_referrers_raw = await ReferralsRepo.list_referrer_stats_since(
        session,
        since_utc=since_utc,
        limit=top_referrers_limit,
    )
    recent_fraud_cases = await ReferralsRepo.list_recent_fraud_cases_since(
        session,
        since_utc=since_utc,
        limit=recent_cases_limit,
    )

    qualified_like_total = (
        status_counts.get("QUALIFIED", 0)
        + status_counts.get("REWARDED", 0)
        + status_counts.get("DEFERRED_LIMIT", 0)
    )
    rewarded_total = status_counts.get("REWARDED", 0)
    rejected_fraud_total = status_counts.get("REJECTED_FRAUD", 0)
    canceled_total = status_counts.get("CANCELED", 0)

    top_referrers: list[dict[str, object]] = []
    for row in top_referrers_raw:
        started_for_referrer = int(row.get("started_total", 0))
        rejected_for_referrer = int(row.get("rejected_fraud_total", 0))
        top_referrers.append(
            {
                **row,
                "rejected_fraud_rate": _safe_rate(
                    numerator=rejected_for_referrer,
                    denominator=started_for_referrer,
                ),
            }
        )

    return ReferralsDashboardSnapshot(
        generated_at=now_utc,
        window_hours=window_hours,
        referrals_started_total=started_total,
        status_counts=status_counts,
        qualified_like_total=qualified_like_total,
        rewarded_total=rewarded_total,
        rejected_fraud_total=rejected_fraud_total,
        canceled_total=canceled_total,
        qualification_rate=_safe_rate(numerator=qualified_like_total, denominator=started_total),
        reward_rate=_safe_rate(numerator=rewarded_total, denominator=started_total),
        fraud_rejected_rate=_safe_rate(numerator=rejected_fraud_total, denominator=started_total),
        top_referrers=top_referrers,
        recent_fraud_cases=recent_fraud_cases,
    )
