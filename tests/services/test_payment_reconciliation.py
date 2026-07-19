from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.services.payment_reconciliation import (
    ALREADY_CREDITED,
    AMBIGUOUS_MATCH,
    AMOUNT_MISMATCH,
    IGNORED_OUTGOING_OR_REFUND,
    NO_DB_PURCHASE,
    PROVIDER_REFUND_REQUIRES_REVIEW,
    USER_MISMATCH,
    WOULD_RECOVER_EXACT_MATCH,
    ReconciliationCandidate,
    classify_star_transaction_dry_run,
)
from app.services.telegram_stars import TelegramStarTransaction


def _transaction(
    *,
    transaction_id: str = "charge-1",
    amount: int = 29,
    telegram_user_id: int = 270,
    incoming: bool = True,
) -> TelegramStarTransaction:
    partner: dict[str, object] = {
        "type": "user",
        "transaction_type": "invoice_payment",
        "user": {"id": telegram_user_id},
        "invoice_payload": "invoice-1",
    }
    return TelegramStarTransaction(
        transaction_id=transaction_id,
        amount=amount,
        transaction_date=datetime(2026, 7, 7, tzinfo=timezone.utc),
        source=partner if incoming else None,
        receiver=None if incoming else partner,
        raw_payload={"id": transaction_id},
    )


def _candidate(
    *,
    telegram_user_id: int = 270,
    amount: int = 29,
    status: str = "PRECHECKOUT_OK",
    charge_id: str | None = None,
    created_at: datetime | None = None,
    invoice_payload: str | None = "invoice-1",
) -> ReconciliationCandidate:
    return ReconciliationCandidate(
        purchase_id=uuid4(),
        user_id=7,
        telegram_user_id=telegram_user_id,
        stars_amount=amount,
        status=status,
        created_at=created_at or datetime(2026, 7, 6, 23, 45, tzinfo=timezone.utc),
        telegram_payment_charge_id=charge_id,
        invoice_payload=invoice_payload,
    )


def test_exact_match_precheckout_is_dry_run_recoverable() -> None:
    candidate = _candidate()

    decision = classify_star_transaction_dry_run(
        transaction=_transaction(),
        candidates=[candidate],
    )

    assert decision.classification == WOULD_RECOVER_EXACT_MATCH
    assert decision.auto_recovery_allowed is False
    assert decision.candidate_purchase_ids == (candidate.purchase_id,)


def test_already_credited_is_noop_classification() -> None:
    candidate = _candidate(status="CREDITED", charge_id="charge-1")

    decision = classify_star_transaction_dry_run(
        transaction=_transaction(),
        candidates=[candidate],
    )

    assert decision.classification == ALREADY_CREDITED
    assert decision.severity == "LOW"


def test_refunded_charge_match_is_resolved_low_severity() -> None:
    candidate = _candidate(status="REFUNDED", charge_id="charge-1")

    decision = classify_star_transaction_dry_run(
        transaction=_transaction(),
        candidates=[candidate],
    )

    assert decision.classification == ALREADY_CREDITED
    assert decision.severity == "LOW"
    assert decision.candidate_purchase_ids == (candidate.purchase_id,)


def test_amount_mismatch_is_review_classification() -> None:
    decision = classify_star_transaction_dry_run(
        transaction=_transaction(amount=99),
        candidates=[_candidate(amount=29)],
    )

    assert decision.classification == AMOUNT_MISMATCH
    assert decision.severity == "HIGH"


def test_user_mismatch_is_review_classification() -> None:
    decision = classify_star_transaction_dry_run(
        transaction=_transaction(telegram_user_id=999),
        candidates=[_candidate(telegram_user_id=270)],
    )

    assert decision.classification == USER_MISMATCH
    assert decision.severity == "HIGH"


def test_two_exact_candidates_are_ambiguous() -> None:
    decision = classify_star_transaction_dry_run(
        transaction=_transaction(),
        candidates=[_candidate(), _candidate()],
    )

    assert decision.classification == AMBIGUOUS_MATCH
    assert decision.severity == "MEDIUM"
    assert len(decision.candidate_purchase_ids) == 2


def test_invoice_payload_mismatch_is_ambiguous_not_exact() -> None:
    decision = classify_star_transaction_dry_run(
        transaction=_transaction(),
        candidates=[_candidate(invoice_payload="other-invoice")],
    )

    assert decision.classification == AMBIGUOUS_MATCH
    assert decision.severity == "MEDIUM"


def test_same_user_amount_outside_time_window_is_ambiguous() -> None:
    old_candidate = _candidate(
        created_at=datetime(2026, 7, 7, tzinfo=timezone.utc) - timedelta(hours=2)
    )

    decision = classify_star_transaction_dry_run(
        transaction=_transaction(),
        candidates=[old_candidate],
    )

    assert decision.classification == AMBIGUOUS_MATCH
    assert decision.auto_recovery_allowed is False


def test_no_db_purchase_is_high_severity() -> None:
    decision = classify_star_transaction_dry_run(
        transaction=_transaction(),
        candidates=[],
    )

    assert decision.classification == NO_DB_PURCHASE
    assert decision.severity == "HIGH"


def test_provider_refund_for_credited_purchase_requires_review() -> None:
    candidate = _candidate(status="CREDITED", charge_id="charge-1")

    decision = classify_star_transaction_dry_run(
        transaction=_transaction(incoming=False),
        candidates=[candidate],
    )

    assert decision.classification == PROVIDER_REFUND_REQUIRES_REVIEW
    assert decision.severity == "HIGH"
    assert decision.candidate_purchase_ids == (candidate.purchase_id,)


def test_provider_refund_for_refunded_purchase_is_resolved_low_severity() -> None:
    candidate = _candidate(status="REFUNDED", charge_id="charge-1")

    decision = classify_star_transaction_dry_run(
        transaction=_transaction(incoming=False),
        candidates=[candidate],
    )

    assert decision.classification == ALREADY_CREDITED
    assert decision.severity == "LOW"
    assert decision.candidate_purchase_ids == (candidate.purchase_id,)


def test_non_invoice_transaction_is_ignored() -> None:
    transaction = _transaction()
    transaction = TelegramStarTransaction(
        transaction_id=transaction.transaction_id,
        amount=transaction.amount,
        transaction_date=transaction.transaction_date,
        source={"type": "user", "transaction_type": "gift", "user": {"id": 270}},
        receiver=None,
        raw_payload=transaction.raw_payload,
    )

    decision = classify_star_transaction_dry_run(
        transaction=transaction,
        candidates=[_candidate()],
    )

    assert decision.classification == IGNORED_OUTGOING_OR_REFUND
    assert decision.auto_recovery_allowed is False
