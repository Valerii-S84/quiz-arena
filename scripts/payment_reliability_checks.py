#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

REQUIRED_ALLOWED_UPDATES = ("message", "callback_query", "pre_checkout_query")
OPTIONAL_ALLOWED_UPDATES = ("my_chat_member",)


@dataclass(frozen=True)
class InvariantCheck:
    name: str
    severity: str
    sql: str
    params: dict[str, object]
    description: str


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    severity: str
    count: int | None
    description: str


def classify_count_result(
    *,
    name: str,
    severity: str,
    count: int,
    description: str,
) -> CheckResult:
    status = "OK" if count == 0 else "FAIL"
    return CheckResult(
        name=name,
        status=status,
        severity=severity,
        count=count,
        description=description,
    )


def evaluate_allowed_updates(allowed_updates: list[str] | None) -> CheckResult:
    configured_updates = set(allowed_updates or [])
    missing_updates = []
    if configured_updates:
        missing_updates = [
            update_type
            for update_type in REQUIRED_ALLOWED_UPDATES
            if update_type not in configured_updates
        ]
    description = (
        "Telegram webhook allowed_updates must include message, callback_query, "
        "and pre_checkout_query for Stars payments and existing callbacks."
    )
    return CheckResult(
        name="payments_webhook_allowed_updates_missing",
        status="OK" if not missing_updates else "FAIL",
        severity="HIGH",
        count=len(missing_updates),
        description=description,
    )


def extract_allowed_updates(webhook_info: dict[str, Any]) -> list[str] | None:
    result = webhook_info.get("result")
    if isinstance(result, dict):
        allowed_updates = result.get("allowed_updates")
    else:
        allowed_updates = webhook_info.get("allowed_updates")
    if not isinstance(allowed_updates, list):
        return None
    return [str(update_type) for update_type in allowed_updates]


def load_webhook_info(path: Path) -> dict[str, Any]:
    raw_payload = sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8")
    loaded = json.loads(raw_payload)
    if not isinstance(loaded, dict):
        raise ValueError("Webhook info JSON must be an object")
    return loaded


def _precheckout_stuck_check(precheckout_cutoff: datetime) -> InvariantCheck:
    return InvariantCheck(
        name="payments_precheckout_stuck_detected",
        severity="HIGH",
        sql="""
            SELECT count(*)
            FROM purchases p
            WHERE p.status = 'PRECHECKOUT_OK'
              AND p.stars_amount > 0
              AND EXISTS (
                SELECT 1
                FROM analytics_events e
                WHERE e.event_type = 'purchase_precheckout_ok'
                  AND e.payload ->> 'purchase_id' = p.id::text
                  AND e.happened_at <= :precheckout_cutoff
              )
        """,
        params={"precheckout_cutoff": precheckout_cutoff},
        description="Paid Stars purchase stuck in PRECHECKOUT_OK older than 3 minutes.",
    )


def _paid_uncredited_stuck_check(paid_uncredited_cutoff: datetime) -> InvariantCheck:
    return InvariantCheck(
        name="payments_paid_uncredited_stuck_detected",
        severity="HIGH",
        sql="""
            SELECT count(*)
            FROM purchases
            WHERE status = 'PAID_UNCREDITED'
              AND stars_amount > 0
              AND paid_at IS NOT NULL
              AND paid_at <= :paid_uncredited_cutoff
        """,
        params={"paid_uncredited_cutoff": paid_uncredited_cutoff},
        description="Paid Stars purchase stuck in PAID_UNCREDITED older than 60 seconds.",
    )


def _credited_premium_missing_entitlement_check() -> InvariantCheck:
    return InvariantCheck(
        name="payments_credited_premium_missing_entitlement",
        severity="HIGH",
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
        params={},
        description="Credited premium purchase has no premium entitlement.",
    )


def _credited_stars_missing_purchase_credit_check() -> InvariantCheck:
    return InvariantCheck(
        name="payments_credited_stars_missing_purchase_credit",
        severity="HIGH",
        sql="""
            SELECT count(*)
            FROM purchases p
            WHERE p.status = 'CREDITED'
              AND p.stars_amount > 0
              AND NOT EXISTS (
                SELECT 1
                FROM ledger_entries l
                WHERE l.purchase_id = p.id
                  AND l.entry_type = 'PURCHASE_CREDIT'
                  AND l.direction = 'CREDIT'
              )
        """,
        params={},
        description="Credited paid Stars purchase has no PURCHASE_CREDIT ledger row.",
    )


def _duplicate_charge_id_check() -> InvariantCheck:
    return InvariantCheck(
        name="payments_duplicate_telegram_payment_charge_id",
        severity="HIGH",
        sql="""
            SELECT COALESCE(SUM(duplicate_count - 1), 0)
            FROM (
              SELECT count(*) AS duplicate_count
              FROM purchases
              WHERE telegram_payment_charge_id IS NOT NULL
              GROUP BY telegram_payment_charge_id
              HAVING count(*) > 1
            ) duplicates
        """,
        params={},
        description="Duplicate telegram_payment_charge_id values exist.",
    )


def _duplicate_active_premium_check(now_utc: datetime) -> InvariantCheck:
    return InvariantCheck(
        name="payments_duplicate_active_premium_entitlements",
        severity="HIGH",
        sql="""
            SELECT COALESCE(SUM(duplicate_count - 1), 0)
            FROM (
              SELECT count(*) AS duplicate_count
              FROM entitlements
              WHERE entitlement_type = 'PREMIUM'
                AND status = 'ACTIVE'
                AND starts_at <= :now_utc
                AND (ends_at IS NULL OR ends_at > :now_utc)
              GROUP BY user_id
              HAVING count(*) > 1
            ) duplicates
        """,
        params={"now_utc": now_utc},
        description="Duplicate active premium entitlements exist for a user.",
    )


def _duplicate_premium_source_purchase_check() -> InvariantCheck:
    return InvariantCheck(
        name="payments_constraint_duplicate_premium_source_purchase",
        severity="HIGH",
        sql="""
            SELECT COALESCE(SUM(duplicate_count - 1), 0)
            FROM (
              SELECT count(*) AS duplicate_count
              FROM entitlements
              WHERE entitlement_type = 'PREMIUM'
                AND source_purchase_id IS NOT NULL
              GROUP BY source_purchase_id
              HAVING count(*) > 1
            ) duplicates
        """,
        params={},
        description=(
            "Constraint preflight: duplicate premium entitlements exist for a source purchase."
        ),
    )


def _duplicate_purchase_credit_ledger_check() -> InvariantCheck:
    return InvariantCheck(
        name="payments_constraint_duplicate_purchase_credit_ledger",
        severity="HIGH",
        sql="""
            SELECT COALESCE(SUM(duplicate_count - 1), 0)
            FROM (
              SELECT count(*) AS duplicate_count
              FROM ledger_entries
              WHERE purchase_id IS NOT NULL
                AND entry_type = 'PURCHASE_CREDIT'
                AND direction = 'CREDIT'
              GROUP BY purchase_id
              HAVING count(*) > 1
            ) duplicates
        """,
        params={},
        description=(
            "Constraint preflight: duplicate PURCHASE_CREDIT ledger rows exist for a purchase."
        ),
    )


def _paid_purchase_missing_charge_id_check() -> InvariantCheck:
    return InvariantCheck(
        name="payments_constraint_paid_purchase_missing_charge_id",
        severity="HIGH",
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
        params={},
        description="Constraint preflight: paid Stars purchase is missing Telegram charge id.",
    )


def _paid_purchase_missing_paid_at_check() -> InvariantCheck:
    return InvariantCheck(
        name="payments_constraint_paid_purchase_missing_paid_at",
        severity="HIGH",
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
              AND paid_at IS NULL
        """,
        params={},
        description="Constraint preflight: paid Stars purchase is missing paid_at timestamp.",
    )


def _credited_purchase_missing_credited_at_check() -> InvariantCheck:
    return InvariantCheck(
        name="payments_constraint_credited_purchase_missing_credited_at",
        severity="HIGH",
        sql="""
            SELECT count(*)
            FROM purchases p
            WHERE p.credited_at IS NULL
              AND (
                p.status = 'CREDITED'
                OR (
                  p.status = 'REFUNDED'
                  AND (
                    EXISTS (
                      SELECT 1
                      FROM ledger_entries l
                      WHERE l.purchase_id = p.id
                        AND l.entry_type = 'PURCHASE_CREDIT'
                        AND l.direction = 'CREDIT'
                    )
                    OR EXISTS (
                      SELECT 1
                      FROM entitlements e
                      WHERE e.source_purchase_id = p.id
                        AND e.entitlement_type = 'PREMIUM'
                    )
                  )
                )
              )
        """,
        params={},
        description=(
            "Constraint preflight: credited purchase is missing credited_at; uncredited refunded "
            "purchases are excluded."
        ),
    )


def build_invariant_checks(now_utc: datetime) -> list[InvariantCheck]:
    precheckout_cutoff = now_utc - timedelta(minutes=3)
    paid_uncredited_cutoff = now_utc - timedelta(seconds=60)
    return [
        _precheckout_stuck_check(precheckout_cutoff),
        _paid_uncredited_stuck_check(paid_uncredited_cutoff),
        _credited_premium_missing_entitlement_check(),
        _credited_stars_missing_purchase_credit_check(),
        _duplicate_charge_id_check(),
        _duplicate_active_premium_check(now_utc),
        _duplicate_premium_source_purchase_check(),
        _duplicate_purchase_credit_ledger_check(),
        _paid_purchase_missing_charge_id_check(),
        _paid_purchase_missing_paid_at_check(),
        _credited_purchase_missing_credited_at_check(),
    ]


def read_only_sql_texts() -> list[str]:
    checks = build_invariant_checks(datetime(2026, 1, 1, tzinfo=timezone.utc))
    return [check.sql for check in checks] + [
        """
        SELECT count(*)
        FROM outbox_events
        WHERE event_type = 'payments_telegram_stars_reconciliation_review'
          AND status = 'OPEN'
        """,
    ]


async def _run_count_check(session: AsyncSession, check: InvariantCheck) -> CheckResult:
    result = await session.execute(text(check.sql), check.params)
    count = int(result.scalar_one() or 0)
    return classify_count_result(
        name=check.name,
        severity=check.severity,
        count=count,
        description=check.description,
    )


async def _run_open_review_check(session: AsyncSession) -> CheckResult:
    description = "Open payment reconciliation reviews exist."
    count_result = await session.execute(
        text(
            """
            SELECT count(*)
            FROM outbox_events
            WHERE event_type = 'payments_telegram_stars_reconciliation_review'
              AND status = 'OPEN'
            """
        )
    )
    count = int(count_result.scalar_one() or 0)
    return classify_count_result(
        name="payments_open_manual_review_records",
        severity="MEDIUM",
        count=count,
        description=description,
    )


async def run_database_checks(now_utc: datetime) -> list[CheckResult]:
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        results = [
            await _run_count_check(session, check) for check in build_invariant_checks(now_utc)
        ]
        results.append(await _run_open_review_check(session))
        await session.rollback()
    return results


def render_text(results: list[CheckResult]) -> str:
    lines = ["payment_reliability_checks:"]
    for result in results:
        count = "n/a" if result.count is None else str(result.count)
        lines.append(
            f"- {result.status} severity={result.severity} "
            f"name={result.name} count={count} description={result.description}"
        )
    return "\n".join(lines)


def exit_code_for(results: list[CheckResult]) -> int:
    return 1 if any(result.status == "FAIL" for result in results) else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run read-only Telegram Stars payment reliability checks."
    )
    parser.add_argument(
        "--webhook-info-json",
        type=Path,
        help="Optional path to getWebhookInfo JSON, or '-' for stdin. No token is required.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Only evaluate webhook info JSON; do not connect to the database.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> list[CheckResult]:
    now_utc = datetime.now(timezone.utc)
    results: list[CheckResult] = []
    if not args.skip_db:
        results.extend(await run_database_checks(now_utc))
    if args.webhook_info_json is not None:
        webhook_info = load_webhook_info(args.webhook_info_json)
        results.append(evaluate_allowed_updates(extract_allowed_updates(webhook_info)))
    return results


def main() -> int:
    args = _parse_args()
    results = asyncio.run(_run(args))
    if args.json:
        sys.stdout.write(json.dumps([asdict(result) for result in results], indent=2))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(results))
        sys.stdout.write("\n")
    return exit_code_for(results)


if __name__ == "__main__":
    raise SystemExit(main())
