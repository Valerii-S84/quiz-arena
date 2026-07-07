from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.services.payment_reconciliation import (
    ALREADY_CREDITED,
    AMBIGUOUS_MATCH,
    AMOUNT_MISMATCH,
    IGNORED_OUTGOING_OR_REFUND,
    NO_DB_PURCHASE,
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
) -> ReconciliationCandidate:
    return ReconciliationCandidate(
        purchase_id=uuid4(),
        user_id=7,
        telegram_user_id=telegram_user_id,
        stars_amount=amount,
        status=status,
        telegram_payment_charge_id=charge_id,
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


def test_no_db_purchase_is_high_severity() -> None:
    decision = classify_star_transaction_dry_run(
        transaction=_transaction(),
        candidates=[],
    )

    assert decision.classification == NO_DB_PURCHASE
    assert decision.severity == "HIGH"


def test_outgoing_or_refund_transaction_is_ignored() -> None:
    decision = classify_star_transaction_dry_run(
        transaction=_transaction(incoming=False),
        candidates=[_candidate()],
    )

    assert decision.classification == IGNORED_OUTGOING_OR_REFUND
    assert decision.auto_recovery_allowed is False
