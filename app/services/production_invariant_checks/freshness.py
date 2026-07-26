from __future__ import annotations

from datetime import date, datetime, timedelta

from app.services.production_invariant_checks.types import (
    SEVERITY_P1,
    SEVERITY_P2,
    InvariantCheck,
    build_check,
)

MANUAL_REVIEW_OUTBOX_EVENT_TYPES = ("payments_telegram_stars_reconciliation_review",)
_QUEUE_OLDEST_MESSAGE_AGE_SQL = """
    SELECT count(*)
    FROM outbox_events
    WHERE status IN ('NEW','PENDING','OPEN','RETRY')
      AND created_at <= :queue_old_cutoff
      AND NOT (
        status = 'OPEN'
        AND event_type IN ('payments_telegram_stars_reconciliation_review')
      )
"""
_STREAK_UPDATE_STALE_SQL = """
    WITH recent_activity AS (
      SELECT user_id, max(answered_at) AS latest_answered_at
      FROM quiz_attempts
      WHERE answered_at >= :streak_activity_cutoff
      GROUP BY user_id
    )
    SELECT count(*)
    FROM recent_activity a
    LEFT JOIN streak_state s ON s.user_id = a.user_id
    WHERE s.user_id IS NULL
       OR s.updated_at < a.latest_answered_at
"""
_GLOBAL_BEST_STREAK_SOURCE_SQL = """
    SELECT count(*)
    FROM streak_state
    WHERE current_streak > best_streak
"""
_ANALYTICS_DAILY_STALE_SQL = """
    SELECT CASE WHEN EXISTS (
      SELECT 1
      FROM analytics_daily
      WHERE local_date_berlin >= :local_today_berlin
        AND calculated_at >= :analytics_fresh_cutoff
    ) THEN 0 ELSE 1 END
"""
_TELEGRAM_DELIVERY_PENDING_STALE_SQL = """
    SELECT count(*)
    FROM telegram_delivery_attempts
    WHERE status = 'PENDING'
      AND updated_at <= :telegram_delivery_pending_cutoff
"""


def build_freshness_checks(now_utc: datetime, local_today_berlin: date) -> list[InvariantCheck]:
    return [
        build_check(
            name="queue_oldest_message_age_seconds",
            severity=SEVERITY_P1,
            sql=_QUEUE_OLDEST_MESSAGE_AGE_SQL,
            params={"queue_old_cutoff": now_utc - timedelta(minutes=15)},
            description="Outbox queue has messages older than 15 minutes.",
            safe_context={
                "manual_review_event_types_excluded": MANUAL_REVIEW_OUTBOX_EVENT_TYPES,
                "exclusion_reason": "operator-owned payment reconciliation reviews stay OPEN",
            },
        ),
        build_check(
            name="streak_update_stale",
            severity=SEVERITY_P1,
            sql=_STREAK_UPDATE_STALE_SQL,
            params={"streak_activity_cutoff": now_utc - timedelta(hours=6)},
            description="Recent quiz activity exists but the same user's streak_state is stale.",
        ),
        build_check(
            name="global_best_streak_source_inconsistent",
            severity=SEVERITY_P1,
            sql=_GLOBAL_BEST_STREAK_SOURCE_SQL,
            description="Global best streak source has rows where current_streak exceeds best_streak.",
        ),
        build_check(
            name="analytics_daily_stale",
            severity=SEVERITY_P2,
            sql=_ANALYTICS_DAILY_STALE_SQL,
            params={
                "local_today_berlin": local_today_berlin,
                "analytics_fresh_cutoff": now_utc - timedelta(hours=2),
            },
            description="Daily analytics aggregate is stale for the Berlin day.",
        ),
        build_check(
            name="telegram_delivery_pending_stale",
            severity=SEVERITY_P2,
            sql=_TELEGRAM_DELIVERY_PENDING_STALE_SQL,
            params={"telegram_delivery_pending_cutoff": now_utc - timedelta(minutes=15)},
            description="Telegram delivery attempt remains pending without a terminal outcome.",
        ),
    ]
