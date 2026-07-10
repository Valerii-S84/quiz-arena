from __future__ import annotations

from datetime import datetime, timedelta

from app.services.production_invariant_checks.types import (
    SEVERITY_P1,
    SEVERITY_P2,
    InvariantCheck,
    build_check,
)


def build_payment_checks(now_utc: datetime) -> list[InvariantCheck]:
    return [
        build_check(
            name="paid_without_entitlement",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM purchases p
                WHERE p.status = 'CREDITED'
                  AND p.product_type = 'PREMIUM'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM entitlements e
                    WHERE e.source_purchase_id = p.id
                      AND e.entitlement_type = 'PREMIUM'
                  )
            """,
            description="Credited premium purchase has no premium entitlement.",
        ),
        build_check(
            name="paid_uncredited_age_minutes",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM purchases
                WHERE status = 'PAID_UNCREDITED'
                  AND stars_amount > 0
                  AND paid_at IS NOT NULL
                  AND paid_at <= :paid_uncredited_cutoff
            """,
            params={"paid_uncredited_cutoff": now_utc - timedelta(minutes=5)},
            description="Paid purchase remains PAID_UNCREDITED longer than 5 minutes.",
        ),
        build_check(
            name="paid_without_charge_id",
            severity=SEVERITY_P1,
            sql="""
                SELECT count(*)
                FROM purchases
                WHERE stars_amount > 0
                  AND status IN (
                    'PAID_UNCREDITED',
                    'FAILED_CREDIT_PENDING_REVIEW',
                    'CREDITED',
                    'REFUNDED'
                  )
                  AND telegram_payment_charge_id IS NULL
            """,
            description="Paid Stars purchase is missing telegram_payment_charge_id.",
        ),
        build_check(
            name="reconciliation_diff_nonzero",
            severity=SEVERITY_P1,
            sql="""
                SELECT COALESCE((
                  SELECT diff_count
                  FROM reconciliation_runs
                  WHERE finished_at IS NOT NULL
                  ORDER BY finished_at DESC, id DESC
                  LIMIT 1
                ), 0)
            """,
            description="Latest completed payment reconciliation has a non-zero diff.",
        ),
        build_check(
            name="expired_active_entitlements_count",
            severity=SEVERITY_P2,
            sql="""
                SELECT count(*)
                FROM entitlements
                WHERE entitlement_type = 'PREMIUM'
                  AND status = 'ACTIVE'
                  AND ends_at IS NOT NULL
                  AND ends_at <= :now_utc
            """,
            params={"now_utc": now_utc},
            description="Expired premium entitlement rows still have ACTIVE status.",
        ),
        build_check(
            name="webhook_processing_failed_or_stuck",
            severity=SEVERITY_P1,
            sql="""
                SELECT (
                  SELECT count(*)
                  FROM processed_updates
                  WHERE status = 'PROCESSING'
                    AND processed_at <= :webhook_processing_cutoff
                ) + (
                  SELECT count(*)
                  FROM outbox_events
                  WHERE event_type = 'telegram_update_failed_final'
                    AND created_at >= :recent_cutoff
                )
            """,
            params={
                "webhook_processing_cutoff": now_utc - timedelta(minutes=10),
                "recent_cutoff": now_utc - timedelta(hours=24),
            },
            description="Telegram update processing is stuck or has final failures.",
        ),
    ]
