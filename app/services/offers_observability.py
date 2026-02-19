from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.offers_repo import OffersRepo


def _safe_rate(*, numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


@dataclass(frozen=True, slots=True)
class OfferFunnelSnapshot:
    generated_at: datetime
    window_hours: int
    impressions_total: int
    unique_users: int
    clicks_total: int
    dismissals_total: int
    conversions_total: int
    click_through_rate: float
    conversion_rate: float
    dismiss_rate: float
    impressions_per_user: float
    top_offer_codes: dict[str, int]


@dataclass(frozen=True, slots=True)
class OfferAlertThresholds:
    min_impressions: int
    min_conversion_rate: float
    max_dismiss_rate: float
    max_impressions_per_user: float


@dataclass(frozen=True, slots=True)
class OfferAlertState:
    conversion_drop_detected: bool
    spam_anomaly_detected: bool
    conversion_rate_below_threshold: bool
    dismiss_rate_above_threshold: bool
    impressions_per_user_above_threshold: bool
    thresholds_applied: bool


def _clamp_non_negative_int(value: object, default: int) -> int:
    if not isinstance(value, int):
        return default
    return max(0, value)


def _clamp_rate(value: object, default: float) -> float:
    if not isinstance(value, (int, float)):
        return default
    return min(1.0, max(0.0, float(value)))


def _clamp_non_negative_float(value: object, default: float) -> float:
    if not isinstance(value, (int, float)):
        return default
    return max(0.0, float(value))


def get_offer_alert_thresholds(settings: object) -> OfferAlertThresholds:
    return OfferAlertThresholds(
        min_impressions=_clamp_non_negative_int(
            getattr(settings, "offers_alert_min_impressions", 50),
            50,
        ),
        min_conversion_rate=_clamp_rate(
            getattr(settings, "offers_alert_min_conversion_rate", 0.03),
            0.03,
        ),
        max_dismiss_rate=_clamp_rate(
            getattr(settings, "offers_alert_max_dismiss_rate", 0.60),
            0.60,
        ),
        max_impressions_per_user=_clamp_non_negative_float(
            getattr(settings, "offers_alert_max_impressions_per_user", 4.0),
            4.0,
        ),
    )


def evaluate_offer_alert_state(
    *,
    snapshot: OfferFunnelSnapshot,
    thresholds: OfferAlertThresholds,
) -> OfferAlertState:
    thresholds_applied = snapshot.impressions_total >= thresholds.min_impressions
    if not thresholds_applied:
        return OfferAlertState(
            conversion_drop_detected=False,
            spam_anomaly_detected=False,
            conversion_rate_below_threshold=False,
            dismiss_rate_above_threshold=False,
            impressions_per_user_above_threshold=False,
            thresholds_applied=False,
        )

    conversion_rate_below_threshold = snapshot.conversion_rate < thresholds.min_conversion_rate
    dismiss_rate_above_threshold = snapshot.dismiss_rate > thresholds.max_dismiss_rate
    impressions_per_user_above_threshold = snapshot.impressions_per_user > thresholds.max_impressions_per_user

    return OfferAlertState(
        conversion_drop_detected=conversion_rate_below_threshold,
        spam_anomaly_detected=dismiss_rate_above_threshold or impressions_per_user_above_threshold,
        conversion_rate_below_threshold=conversion_rate_below_threshold,
        dismiss_rate_above_threshold=dismiss_rate_above_threshold,
        impressions_per_user_above_threshold=impressions_per_user_above_threshold,
        thresholds_applied=True,
    )


async def build_offer_funnel_snapshot(
    session: AsyncSession,
    *,
    now_utc: datetime,
    window_hours: int,
    top_codes_limit: int = 10,
) -> OfferFunnelSnapshot:
    since_utc = now_utc - timedelta(hours=window_hours)
    impressions_total = await OffersRepo.count_impressions_since(session, shown_since_utc=since_utc)
    unique_users = await OffersRepo.count_distinct_users_since(session, shown_since_utc=since_utc)
    clicks_total = await OffersRepo.count_clicked_since(session, shown_since_utc=since_utc)
    dismissals_total = await OffersRepo.count_dismissed_since(session, shown_since_utc=since_utc)
    conversions_total = await OffersRepo.count_converted_since(session, shown_since_utc=since_utc)
    top_offer_codes = await OffersRepo.count_impressions_by_offer_code_since(
        session,
        shown_since_utc=since_utc,
        limit=top_codes_limit,
    )

    return OfferFunnelSnapshot(
        generated_at=now_utc,
        window_hours=window_hours,
        impressions_total=impressions_total,
        unique_users=unique_users,
        clicks_total=clicks_total,
        dismissals_total=dismissals_total,
        conversions_total=conversions_total,
        click_through_rate=_safe_rate(numerator=clicks_total, denominator=impressions_total),
        conversion_rate=_safe_rate(numerator=conversions_total, denominator=impressions_total),
        dismiss_rate=_safe_rate(numerator=dismissals_total, denominator=impressions_total),
        impressions_per_user=_safe_rate(numerator=impressions_total, denominator=max(1, unique_users)),
        top_offer_codes=top_offer_codes,
    )
