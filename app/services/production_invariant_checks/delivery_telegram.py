from __future__ import annotations

from datetime import datetime, timedelta

from app.services.production_invariant_checks.types import (
    SEVERITY_P1,
    SEVERITY_P2,
    InvariantCheck,
    build_check,
)


def build_telegram_delivery_checks(now_utc: datetime) -> list[InvariantCheck]:
    return [
        build_check(
            name="telegram_delivery_failure_rate",
            severity=SEVERITY_P1,
            sql="""
                WITH recent AS (
                  SELECT
                    count(*) AS total,
                    count(*) FILTER (WHERE status = 'FAILED') AS failed
                  FROM telegram_delivery_attempts
                  WHERE coalesce(failed_at, updated_at, created_at) >= :delivery_window_start
                )
                SELECT CASE
                  WHEN total >= :min_delivery_attempts
                   AND (failed * 100) >= (total * :failure_rate_percent)
                  THEN 1 ELSE 0 END
                FROM recent
            """,
            params={
                "delivery_window_start": now_utc - timedelta(hours=1),
                "min_delivery_attempts": 10,
                "failure_rate_percent": 20,
            },
            description="Telegram delivery failure rate is at least 20 percent over 1 hour.",
        ),
        build_check(
            name="telegram_blocked_users_count",
            severity=SEVERITY_P2,
            sql="""
                WITH blocked_candidates AS (
                  SELECT
                    telegram_user_id,
                    max(coalesce(failed_at, updated_at, created_at)) AS blocked_at
                  FROM telegram_delivery_attempts
                  WHERE status = 'FAILED'
                    AND is_blocked_candidate IS TRUE
                    AND telegram_user_id IS NOT NULL
                    AND coalesce(failed_at, updated_at, created_at) >= :blocked_since
                  GROUP BY telegram_user_id
                )
                SELECT count(*)
                FROM blocked_candidates b
                WHERE NOT EXISTS (
                  SELECT 1
                  FROM users u
                  WHERE u.telegram_user_id = b.telegram_user_id
                    AND u.last_seen_at IS NOT NULL
                    AND u.last_seen_at > b.blocked_at
                )
            """,
            params={"blocked_since": now_utc - timedelta(days=30)},
            description="Telegram blocked/chat-not-found candidates require manual review.",
        ),
    ]
