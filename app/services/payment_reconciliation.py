from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.services.telegram_stars import TelegramStarTransaction

EXACT_MATCH_WINDOW = timedelta(minutes=30)
RECOVERABLE_RECONCILIATION_STATUSES = frozenset(
    {"PRECHECKOUT_OK", "INVOICE_SENT", "CREATED", "PAID_UNCREDITED"}
)
RESOLVED_RECONCILIATION_STATUSES = frozenset({"CREDITED", "REFUNDED"})

ALREADY_CREDITED = "ALREADY_CREDITED"
WOULD_RECOVER_EXACT_MATCH = "WOULD_RECOVER_EXACT_MATCH"
PROVIDER_REFUND_REQUIRES_REVIEW = "PROVIDER_REFUND_REQUIRES_REVIEW"
AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
NO_DB_PURCHASE = "NO_DB_PURCHASE"
AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
USER_MISMATCH = "USER_MISMATCH"
IGNORED_OUTGOING_OR_REFUND = "IGNORED_OUTGOING_OR_REFUND"


@dataclass(frozen=True)
class ReconciliationCandidate:
    purchase_id: UUID
    user_id: int
    telegram_user_id: int
    stars_amount: int
    status: str
    created_at: datetime
    telegram_payment_charge_id: str | None = None
    invoice_payload: str | None = None


@dataclass(frozen=True)
class ReconciliationDecision:
    classification: str
    severity: str
    transaction_id: str
    transaction_amount: int
    transaction_date: datetime
    transaction_user_id: int | None
    transaction_type: str | None
    transaction_is_incoming: bool
    candidate_purchase_ids: tuple[UUID, ...]
    auto_recovery_allowed: bool = False


def classify_star_transaction_dry_run(
    *,
    transaction: TelegramStarTransaction,
    candidates: list[ReconciliationCandidate],
) -> ReconciliationDecision:
    if _should_ignore_transaction(transaction):
        return _decision(IGNORED_OUTGOING_OR_REFUND, "LOW", transaction, candidates=[])

    if _is_provider_refund_transaction(transaction):
        return _classify_provider_refund_transaction(transaction, candidates)

    resolved_match = _resolved_charge_match(transaction, candidates)
    if resolved_match is not None:
        return _decision(ALREADY_CREDITED, "LOW", transaction, candidates=[resolved_match])

    if not candidates:
        return _decision(NO_DB_PURCHASE, "HIGH", transaction, candidates=[])

    exact_candidates = [
        candidate for candidate in candidates if _is_exact_recoverable_match(transaction, candidate)
    ]
    if len(exact_candidates) == 1:
        return _decision(
            WOULD_RECOVER_EXACT_MATCH,
            "HIGH",
            transaction,
            candidates=exact_candidates,
        )
    if len(exact_candidates) > 1:
        return _decision(AMBIGUOUS_MATCH, "MEDIUM", transaction, candidates=exact_candidates)

    if _has_same_user_amount_candidate(transaction, candidates):
        return _decision(AMBIGUOUS_MATCH, "MEDIUM", transaction, candidates=candidates)
    if _has_same_user_candidate(transaction, candidates):
        return _decision(AMOUNT_MISMATCH, "HIGH", transaction, candidates=candidates)
    return _decision(USER_MISMATCH, "HIGH", transaction, candidates=candidates)


def _should_ignore_transaction(transaction: TelegramStarTransaction) -> bool:
    return transaction.transaction_type != "invoice_payment"


def _is_provider_refund_transaction(transaction: TelegramStarTransaction) -> bool:
    return not transaction.is_incoming and transaction.transaction_type == "invoice_payment"


def _classify_provider_refund_transaction(
    transaction: TelegramStarTransaction,
    candidates: list[ReconciliationCandidate],
) -> ReconciliationDecision:
    refunded_match = _refunded_charge_match(transaction, candidates)
    if refunded_match is not None:
        return _decision(ALREADY_CREDITED, "LOW", transaction, candidates=[refunded_match])
    if not candidates:
        return _decision(NO_DB_PURCHASE, "HIGH", transaction, candidates=[])
    charge_matches = _charge_matches(transaction, candidates)
    return _decision(
        PROVIDER_REFUND_REQUIRES_REVIEW,
        "HIGH",
        transaction,
        candidates=charge_matches or candidates,
    )


def _resolved_charge_match(
    transaction: TelegramStarTransaction,
    candidates: list[ReconciliationCandidate],
) -> ReconciliationCandidate | None:
    for candidate in candidates:
        if (
            candidate.telegram_payment_charge_id == transaction.transaction_id
            and candidate.status in RESOLVED_RECONCILIATION_STATUSES
        ):
            return candidate
    return None


def _refunded_charge_match(
    transaction: TelegramStarTransaction,
    candidates: list[ReconciliationCandidate],
) -> ReconciliationCandidate | None:
    for candidate in candidates:
        if (
            candidate.telegram_payment_charge_id == transaction.transaction_id
            and candidate.status == "REFUNDED"
        ):
            return candidate
    return None


def _charge_matches(
    transaction: TelegramStarTransaction,
    candidates: list[ReconciliationCandidate],
) -> list[ReconciliationCandidate]:
    return [
        candidate
        for candidate in candidates
        if candidate.telegram_payment_charge_id == transaction.transaction_id
    ]


def _is_exact_recoverable_match(
    transaction: TelegramStarTransaction,
    candidate: ReconciliationCandidate,
) -> bool:
    return (
        candidate.telegram_user_id == transaction.source_user_id
        and candidate.stars_amount == transaction.amount
        and candidate.status in RECOVERABLE_RECONCILIATION_STATUSES
        and candidate.telegram_payment_charge_id in (None, transaction.transaction_id)
        and transaction.invoice_payload is not None
        and candidate.invoice_payload == transaction.invoice_payload
        and _is_within_match_window(transaction, candidate)
    )


def _is_within_match_window(
    transaction: TelegramStarTransaction,
    candidate: ReconciliationCandidate,
) -> bool:
    return (
        candidate.created_at
        <= transaction.transaction_date
        <= (candidate.created_at + EXACT_MATCH_WINDOW)
    )


def _has_same_user_amount_candidate(
    transaction: TelegramStarTransaction,
    candidates: list[ReconciliationCandidate],
) -> bool:
    return any(
        candidate.telegram_user_id == transaction.source_user_id
        and candidate.stars_amount == transaction.amount
        for candidate in candidates
    )


def _has_same_user_candidate(
    transaction: TelegramStarTransaction,
    candidates: list[ReconciliationCandidate],
) -> bool:
    return any(candidate.telegram_user_id == transaction.source_user_id for candidate in candidates)


def _decision(
    classification: str,
    severity: str,
    transaction: TelegramStarTransaction,
    *,
    candidates: list[ReconciliationCandidate],
) -> ReconciliationDecision:
    return ReconciliationDecision(
        classification=classification,
        severity=severity,
        transaction_id=transaction.transaction_id,
        transaction_amount=transaction.amount,
        transaction_date=transaction.transaction_date,
        transaction_user_id=transaction.partner_user_id,
        transaction_type=transaction.transaction_type,
        transaction_is_incoming=transaction.is_incoming,
        candidate_purchase_ids=tuple(candidate.purchase_id for candidate in candidates),
    )
