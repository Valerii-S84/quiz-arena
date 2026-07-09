from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.db.models.payment_inbox import (
    PaymentEvent,
    PaymentReconciliationReview,
    TelegramUpdateInbox,
)
from app.db.repo.payment_inbox_repo import (
    PaymentEventsRepo,
    PaymentReconciliationReviewsRepo,
    TelegramUpdateInboxRepo,
)
from tests.db.repo._helpers import RecordingSession
from tests.type_helpers import ScalarResult


def compile_parameterized_statement(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


async def test_telegram_update_inbox_create_once_uses_update_id_conflict_key() -> None:
    row = TelegramUpdateInbox(
        update_id=1001,
        update_kind="message.successful_payment",
        idempotency_key="telegram-update:1001",
        payload_hash="payload-hash",
        sanitized_evidence={"raw_payload_stored": False},
    )
    session = RecordingSession(ScalarResult(row))

    created, was_created = await TelegramUpdateInboxRepo.create_once(
        session,
        update_id=1001,
        update_kind="message.successful_payment",
        idempotency_key="telegram-update:1001",
        payload_hash="payload-hash",
        sanitized_evidence={"raw_payload_stored": False},
    )

    assert created is row
    assert was_created is True
    sql = compile_parameterized_statement(session.statement)
    assert "INSERT INTO telegram_update_inbox" in sql
    assert "ON CONFLICT (update_id) DO NOTHING" in sql
    assert "raw_payload" not in sql


async def test_payment_event_create_once_uses_idempotency_key() -> None:
    row = PaymentEvent(
        provider="TELEGRAM",
        event_type="SUCCESSFUL_PAYMENT",
        idempotency_key="payment-event:1001:success",
        source_inbox_update_id=1001,
        invoice_payload="inv-1",
        provider_charge_id_hash="charge-hash",
        provider_payment_charge_id_hash="provider-hash",
        currency="XTR",
        total_amount=29,
        telegram_user_id=270,
        safe_payload={"raw_payload_stored": False},
    )
    session = RecordingSession(ScalarResult(row))

    created, was_created = await PaymentEventsRepo.create_once(
        session,
        provider="TELEGRAM",
        event_type="SUCCESSFUL_PAYMENT",
        idempotency_key="payment-event:1001:success",
        source_inbox_update_id=1001,
        invoice_payload="inv-1",
        provider_charge_id_hash="charge-hash",
        provider_payment_charge_id_hash="provider-hash",
        currency="XTR",
        total_amount=29,
        telegram_user_id=270,
        safe_payload={"raw_payload_stored": False},
    )

    assert created is row
    assert was_created is True
    sql = compile_parameterized_statement(session.statement)
    assert "INSERT INTO payment_events" in sql
    assert "ON CONFLICT (idempotency_key) DO NOTHING" in sql
    assert "provider_charge_id_hash" in sql
    assert "telegram_payment_charge_id" not in sql


async def test_payment_review_create_once_uses_unique_key() -> None:
    purchase_id = uuid4()
    row = PaymentReconciliationReview(
        unique_key="review:missing_total:inv-hash",
        review_type="SUCCESSFUL_PAYMENT_VALIDATION",
        severity="HIGH",
        reason="MISSING_TOTAL_AMOUNT",
        purchase_id=purchase_id,
        transaction_id_hash="charge-hash",
        safe_payload={"raw_payload_stored": False},
    )
    session = RecordingSession(ScalarResult(row))

    created, was_created = await PaymentReconciliationReviewsRepo.create_once(
        session,
        unique_key="review:missing_total:inv-hash",
        review_type="SUCCESSFUL_PAYMENT_VALIDATION",
        severity="HIGH",
        reason="MISSING_TOTAL_AMOUNT",
        purchase_id=purchase_id,
        transaction_id_hash="charge-hash",
        safe_payload={"raw_payload_stored": False},
    )

    assert created is row
    assert was_created is True
    sql = compile_parameterized_statement(session.statement)
    assert "INSERT INTO payment_reconciliation_reviews" in sql
    assert "ON CONFLICT (unique_key) DO NOTHING" in sql
    assert "safe_payload" in sql
