from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Request

from app.db.repo.promo_repo import PromoRepo
from app.db.session import SessionLocal

from .internal_promo_constants import (
    PROMO_FAILURE_RESULTS,
    PROMO_GUARD_LOOKBACK_MINUTES,
    PROMO_GUARD_MIN_DISTINCT_USERS,
    PROMO_GUARD_MIN_FAILED_ATTEMPTS,
)
from .internal_promo_helpers import _assert_internal_access, _safe_rate
from .internal_promo_models import PromoDashboardResponse


async def get_promo_dashboard(
    *,
    request: Request,
    window_hours: int,
) -> PromoDashboardResponse:
    _assert_internal_access(request)

    now_utc = datetime.now(timezone.utc)
    window_since_utc = now_utc - timedelta(hours=window_hours)
    guard_since_utc = now_utc - timedelta(minutes=PROMO_GUARD_LOOKBACK_MINUTES)

    async with SessionLocal.begin() as session:
        attempt_counts = await PromoRepo.count_attempts_by_result(
            session, since_utc=window_since_utc
        )
        redemption_counts = await PromoRepo.count_redemptions_by_status(
            session, since_utc=window_since_utc
        )
        discount_redemption_counts = await PromoRepo.count_discount_redemptions_by_status(
            session,
            since_utc=window_since_utc,
        )
        campaign_counts = await PromoRepo.count_campaigns_by_status(session)
        paused_recent = await PromoRepo.count_paused_campaigns_since(
            session, since_utc=window_since_utc
        )
        guard_trigger_hashes = await PromoRepo.count_abusive_code_hashes(
            session,
            since_utc=guard_since_utc,
            min_failed_attempts=PROMO_GUARD_MIN_FAILED_ATTEMPTS,
            min_distinct_users=PROMO_GUARD_MIN_DISTINCT_USERS,
        )

    attempts_total = sum(attempt_counts.values())
    attempts_accepted = attempt_counts.get("ACCEPTED", 0)
    attempts_failed = max(0, attempts_total - attempts_accepted)

    redemptions_total = sum(redemption_counts.values())
    redemptions_applied = redemption_counts.get("APPLIED", 0)

    discount_redemptions_total = sum(discount_redemption_counts.values())
    discount_redemptions_applied = discount_redemption_counts.get("APPLIED", 0)
    discount_redemptions_reserved = discount_redemption_counts.get("RESERVED", 0)
    discount_redemptions_expired = discount_redemption_counts.get("EXPIRED", 0)

    return PromoDashboardResponse(
        generated_at=now_utc,
        window_hours=window_hours,
        attempts_total=attempts_total,
        attempts_accepted=attempts_accepted,
        attempts_failed=attempts_failed,
        acceptance_rate=_safe_rate(numerator=attempts_accepted, denominator=attempts_total),
        failure_rate=_safe_rate(numerator=attempts_failed, denominator=attempts_total),
        attempt_failures_by_result={
            result: attempt_counts.get(result, 0) for result in PROMO_FAILURE_RESULTS
        },
        redemptions_total=redemptions_total,
        redemptions_applied=redemptions_applied,
        redemptions_by_status=redemption_counts,
        discount_redemptions_total=discount_redemptions_total,
        discount_redemptions_applied=discount_redemptions_applied,
        discount_redemptions_reserved=discount_redemptions_reserved,
        discount_redemptions_expired=discount_redemptions_expired,
        discount_conversion_rate=_safe_rate(
            numerator=discount_redemptions_applied,
            denominator=discount_redemptions_total,
        ),
        guard_window_minutes=PROMO_GUARD_LOOKBACK_MINUTES,
        guard_trigger_hashes=guard_trigger_hashes,
        active_campaigns_total=campaign_counts.get("ACTIVE", 0),
        paused_campaigns_total=campaign_counts.get("PAUSED", 0),
        paused_campaigns_recent=paused_recent,
    )
