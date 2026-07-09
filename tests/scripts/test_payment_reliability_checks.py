from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from scripts.payment_reliability_checks import (
    build_invariant_checks,
    evaluate_allowed_updates,
    extract_allowed_updates,
    read_only_sql_texts,
    render_text,
)


def _check_sql(name: str) -> str:
    checks = build_invariant_checks(datetime(2026, 1, 1, tzinfo=timezone.utc))
    for check in checks:
        if check.name == name:
            return check.sql
    raise AssertionError(f"Missing check: {name}")


def _credited_at_preflight_count(
    *,
    status: str,
    credited_at: str | None,
    has_purchase_credit: bool = False,
    has_premium_entitlement: bool = False,
) -> int:
    with sqlite3.connect(":memory:") as connection:
        connection.executescript(
            """
            CREATE TABLE purchases (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                credited_at TEXT
            );
            CREATE TABLE ledger_entries (
                purchase_id TEXT,
                entry_type TEXT NOT NULL,
                direction TEXT NOT NULL
            );
            CREATE TABLE entitlements (
                source_purchase_id TEXT,
                entitlement_type TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO purchases (id, status, credited_at) VALUES (?, ?, ?)",
            ("purchase-1", status, credited_at),
        )
        if has_purchase_credit:
            connection.execute(
                """
                INSERT INTO ledger_entries (purchase_id, entry_type, direction)
                VALUES (?, 'PURCHASE_CREDIT', 'CREDIT')
                """,
                ("purchase-1",),
            )
        if has_premium_entitlement:
            connection.execute(
                """
                INSERT INTO entitlements (source_purchase_id, entitlement_type)
                VALUES (?, 'PREMIUM')
                """,
                ("purchase-1",),
            )
        result = connection.execute(
            _check_sql("payments_constraint_credited_purchase_missing_credited_at")
        )
        return int(result.fetchone()[0])


def test_allowed_updates_missing_message_fails() -> None:
    result = evaluate_allowed_updates(["callback_query", "pre_checkout_query"])

    assert result.status == "FAIL"
    assert result.name == "payments_webhook_allowed_updates_missing"
    assert result.count == 1


def test_allowed_updates_missing_precheckout_fails() -> None:
    result = evaluate_allowed_updates(["message", "callback_query"])

    assert result.status == "FAIL"
    assert result.count == 1


def test_allowed_updates_none_uses_telegram_default_set() -> None:
    result = evaluate_allowed_updates(None)

    assert result.status == "OK"
    assert result.count == 0


def test_allowed_updates_empty_list_uses_telegram_default_set() -> None:
    result = evaluate_allowed_updates([])

    assert result.status == "OK"
    assert result.count == 0


def test_allowed_updates_ok_when_payment_and_callbacks_are_present() -> None:
    result = evaluate_allowed_updates(
        ["message", "callback_query", "pre_checkout_query", "my_chat_member"]
    )

    assert result.status == "OK"
    assert result.count == 0


def test_extract_allowed_updates_from_get_webhook_info_result() -> None:
    payload = {
        "ok": True,
        "result": {
            "url": "https://example.invalid/webhook/telegram",
            "allowed_updates": ["message", "callback_query", "pre_checkout_query"],
        },
    }

    assert extract_allowed_updates(payload) == [
        "message",
        "callback_query",
        "pre_checkout_query",
    ]


def test_read_only_sql_texts_do_not_contain_mutating_statements() -> None:
    forbidden = re.compile(
        r"\b(insert|update|delete|merge|alter|drop|create|truncate|grant|revoke)\b",
        re.IGNORECASE,
    )

    assert read_only_sql_texts()
    for sql in read_only_sql_texts():
        assert forbidden.search(sql) is None


def test_constraint_preflight_checks_are_included() -> None:
    names = {
        check.name for check in build_invariant_checks(datetime(2026, 1, 1, tzinfo=timezone.utc))
    }

    assert {
        "payments_constraint_duplicate_premium_source_purchase",
        "payments_constraint_duplicate_purchase_credit_ledger",
        "payments_constraint_paid_purchase_missing_charge_id",
        "payments_constraint_paid_purchase_missing_paid_at",
        "payments_constraint_credited_purchase_missing_credited_at",
    }.issubset(names)


def test_precheckout_stuck_check_ages_from_precheckout_event() -> None:
    sql = _check_sql("payments_precheckout_stuck_detected")

    assert "analytics_events" in sql
    assert "purchase_precheckout_ok" in sql
    assert "e.happened_at <= :precheckout_cutoff" in sql
    assert "created_at <= :precheckout_cutoff" not in sql


def test_duplicate_active_premium_check_uses_current_entitlement_window() -> None:
    sql = _check_sql("payments_duplicate_active_premium_entitlements")

    assert "starts_at <= :now_utc" in sql
    assert "(ends_at IS NULL OR ends_at > :now_utc)" in sql


def test_open_review_check_reads_current_outbox_mechanism() -> None:
    sql_text = "\n".join(read_only_sql_texts())

    assert "outbox_events" in sql_text
    assert "payments_telegram_stars_reconciliation_review" in sql_text
    assert "payment_reconciliation_reviews" not in sql_text


def test_paid_preflights_include_review_pending_paid_rows() -> None:
    for check_name in (
        "payments_constraint_paid_purchase_missing_charge_id",
        "payments_constraint_paid_purchase_missing_paid_at",
    ):
        assert "FAILED_CREDIT_PENDING_REVIEW" in _check_sql(check_name)


def test_credited_at_preflight_allows_uncredited_refunded_purchase() -> None:
    count = _credited_at_preflight_count(status="REFUNDED", credited_at=None)

    assert count == 0


def test_credited_at_preflight_flags_credited_purchase_missing_credited_at() -> None:
    count = _credited_at_preflight_count(status="CREDITED", credited_at=None)

    assert count == 1


def test_credited_at_preflight_flags_refunded_credit_missing_credited_at() -> None:
    count = _credited_at_preflight_count(
        status="REFUNDED",
        credited_at=None,
        has_purchase_credit=True,
    )

    assert count == 1


def test_credited_at_preflight_allows_refunded_credit_with_credited_at() -> None:
    count = _credited_at_preflight_count(
        status="REFUNDED",
        credited_at="2026-01-01T00:00:00+00:00",
        has_premium_entitlement=True,
    )

    assert count == 0


def test_text_renderer_uses_counts_without_raw_payloads() -> None:
    result = evaluate_allowed_updates(["message"])

    rendered = render_text([result])

    assert "payments_webhook_allowed_updates_missing" in rendered
    assert "count=2" in rendered
    assert "secret" not in rendered.lower()
    assert "token" not in rendered.lower()
