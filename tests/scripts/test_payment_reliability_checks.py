from __future__ import annotations

import re
from datetime import datetime, timezone

from scripts.payment_reliability_checks import (
    build_invariant_checks,
    evaluate_allowed_updates,
    extract_allowed_updates,
    read_only_sql_texts,
    render_text,
)


def test_allowed_updates_missing_message_fails() -> None:
    result = evaluate_allowed_updates(["callback_query", "pre_checkout_query"])

    assert result.status == "FAIL"
    assert result.name == "payments_webhook_allowed_updates_missing"
    assert result.count == 1


def test_allowed_updates_missing_precheckout_fails() -> None:
    result = evaluate_allowed_updates(["message", "callback_query"])

    assert result.status == "FAIL"
    assert result.count == 1


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
    }.issubset(names)


def test_text_renderer_uses_counts_without_raw_payloads() -> None:
    result = evaluate_allowed_updates(["message"])

    rendered = render_text([result])

    assert "payments_webhook_allowed_updates_missing" in rendered
    assert "count=2" in rendered
    assert "secret" not in rendered.lower()
    assert "token" not in rendered.lower()
