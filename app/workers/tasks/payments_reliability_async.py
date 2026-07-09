from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.purchases import Purchase
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.outbox_events_repo import OutboxEventsRepo
from app.db.repo.promo_repo import PromoRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.session import SessionLocal
from app.economy.purchases.catalog import get_product
from app.economy.purchases.errors import (
    ProductNotFoundError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
)
from app.economy.purchases.recovery import MAX_CREDIT_RECOVERY_ATTEMPTS, increment_recovery_failures
from app.economy.purchases.service import PurchaseService
from app.services.alerts import send_ops_alert
from app.services.payment_reconciliation import (
    ALREADY_CREDITED,
    EXACT_MATCH_WINDOW,
    WOULD_RECOVER_EXACT_MATCH,
    ReconciliationCandidate,
    ReconciliationDecision,
    classify_star_transaction_dry_run,
)
from app.services.telegram_stars import (
    TelegramStarsClient,
    TelegramStarsClientError,
    TelegramStarTransaction,
)
from app.workers.tasks.payments_reliability_reconciliation import (
    run_payments_reconciliation_async as run_payments_reconciliation_async,
)

logger = structlog.get_logger("app.workers.tasks.payments_reliability")
PAYMENT_STARS_RECONCILIATION_REVIEW_EVENT = "payments_telegram_stars_reconciliation_review"
PAYMENT_STARS_AUTO_RECOVERED_EVENT = "payments_telegram_star_auto_recovered"
_REVIEWABLE_SEVERITIES = frozenset({"HIGH", "MEDIUM"})
_AUTO_RECOVERY_SUCCESS_OUTCOMES = frozenset({"auto_recovered", "already_credited"})
_TELEGRAM_STARS_RECONCILIATION_PAGE_LIMIT = 100
_TELEGRAM_STARS_RECONCILIATION_MAX_PAGES = 5

__all__ = [
    "expire_stale_unpaid_invoices_async",
    "recover_paid_uncredited_async",
    "run_telegram_stars_reconciliation_async",
    "run_payments_reconciliation_async",
    "run_refund_promo_rollback_async",
]


async def expire_stale_unpaid_invoices_async(*, stale_minutes: int = 30) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    stale_cutoff = now_utc - timedelta(minutes=stale_minutes)

    async with SessionLocal.begin() as session:
        expired_invoices = await PurchasesRepo.expire_stale_unpaid_invoices(
            session,
            older_than_utc=stale_cutoff,
        )

    result = {"expired_invoices": expired_invoices}
    logger.info("stale_unpaid_invoices_expiry_finished", **result)
    return result


async def run_refund_promo_rollback_async(*, batch_size: int = 100) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        purchase_ids = await PromoRepo.get_refunded_purchase_ids_with_pending_redemption_revoke(
            session,
            limit=batch_size,
        )

    summary: dict[str, int] = {
        "examined": len(purchase_ids),
        "rolled_back": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 0,
    }

    for purchase_id in purchase_ids:
        try:
            outcome: str | None = None
            async with SessionLocal.begin() as session:
                purchase = await PurchasesRepo.get_by_id_for_update(session, purchase_id)
                if purchase is None:
                    outcome = "missing"
                elif purchase.status != "REFUNDED" or purchase.applied_promo_code_id is None:
                    outcome = "skipped"
                else:
                    _, _, rollback_applied = await PromoRepo.revoke_redemption_for_refund(
                        session,
                        purchase_id=purchase.id,
                        promo_code_id=purchase.applied_promo_code_id,
                        now_utc=now_utc,
                    )
                    outcome = "rolled_back" if rollback_applied else "skipped"
            if outcome is not None:
                summary[outcome] += 1
        except Exception:
            summary["errors"] += 1
            logger.exception("promo_refund_rollback_error", purchase_id=str(purchase_id))

    logger.info("promo_refund_rollback_finished", **summary)
    return summary


async def _recover_single_purchase(purchase_id: UUID, *, now_utc: datetime) -> str:
    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_for_credit_lock(session, purchase_id)
        if purchase is None:
            return "missing"
        if purchase.status != "PAID_UNCREDITED":
            return "skipped"

        if purchase.telegram_payment_charge_id is None:
            purchase.status = "FAILED_CREDIT_PENDING_REVIEW"
            return "review"
        if not isinstance(purchase.raw_successful_payment, dict):
            purchase.status = "FAILED_CREDIT_PENDING_REVIEW"
            return "review"

        try:
            await PurchaseService.apply_successful_payment(
                session,
                user_id=purchase.user_id,
                invoice_payload=purchase.invoice_payload,
                telegram_payment_charge_id=purchase.telegram_payment_charge_id,
                raw_successful_payment=purchase.raw_successful_payment,
                now_utc=now_utc,
            )
        except (
            ProductNotFoundError,
            PurchaseNotFoundError,
            PurchasePrecheckoutValidationError,
        ):
            payload, failures = increment_recovery_failures(purchase.raw_successful_payment)
            purchase.raw_successful_payment = payload

            if failures >= MAX_CREDIT_RECOVERY_ATTEMPTS:
                purchase.status = "FAILED_CREDIT_PENDING_REVIEW"
                return "review"

            return "retryable_failure"

    return "credited"


async def recover_paid_uncredited_async(
    *, batch_size: int = 100, stale_minutes: int = 2
) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    stale_cutoff = now_utc - timedelta(minutes=stale_minutes)
    logger.info(
        "payment_recovery_started",
        batch_size=batch_size,
        stale_minutes=stale_minutes,
    )

    async with SessionLocal.begin() as session:
        candidates = await PurchasesRepo.get_paid_uncredited_older_than(
            session,
            older_than_utc=stale_cutoff,
            limit=batch_size,
        )

    summary: dict[str, int] = {
        "examined": len(candidates),
        "credited": 0,
        "review": 0,
        "retryable_failure": 0,
        "skipped": 0,
        "missing": 0,
        "errors": 0,
    }

    for purchase in candidates:
        try:
            outcome = await _recover_single_purchase(purchase.id, now_utc=now_utc)
        except Exception as exc:
            summary["errors"] += 1
            logger.warning(
                "payment_recovery_failed",
                purchase_id=str(purchase.id),
                outcome="error",
                error_type=type(exc).__name__,
            )
            logger.exception("paid_uncredited_recovery_error", purchase_id=str(purchase.id))
            continue

        summary[outcome] = summary.get(outcome, 0) + 1
        if outcome in {"review", "retryable_failure"}:
            logger.warning(
                "payment_recovery_failed",
                purchase_id=str(purchase.id),
                outcome=outcome,
            )

    if summary["review"] > 0 or summary["errors"] > 0:
        payload: dict[str, object] = {key: value for key, value in summary.items()}
        await send_ops_alert(
            event="payments_recovery_review_required",
            payload=payload,
        )

    logger.info("payment_recovery_finished", **summary)
    logger.info("paid_uncredited_recovery_finished", **summary)
    return summary


async def run_payment_invariant_alerts_async(
    *,
    precheckout_stale_minutes: int = 3,
    paid_uncredited_stale_seconds: int = 60,
) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    precheckout_cutoff = now_utc - timedelta(minutes=precheckout_stale_minutes)
    paid_uncredited_cutoff = now_utc - timedelta(seconds=paid_uncredited_stale_seconds)

    async with SessionLocal.begin() as session:
        precheckout_stuck = await PurchasesRepo.count_precheckout_ok_older_than(
            session,
            older_than_utc=precheckout_cutoff,
        )
        paid_uncredited_stuck = await PurchasesRepo.count_paid_uncredited_older_than(
            session,
            older_than_utc=paid_uncredited_cutoff,
        )
        credited_premium_missing_entitlement = (
            await PurchasesRepo.count_credited_premium_without_entitlement(session)
        )
        credited_stars_missing_purchase_credit = (
            await PurchasesRepo.count_credited_stars_without_purchase_credit(session)
        )

    summary = {
        "precheckout_stuck": precheckout_stuck,
        "paid_uncredited_stuck": paid_uncredited_stuck,
        "credited_premium_missing_entitlement": credited_premium_missing_entitlement,
        "credited_stars_missing_purchase_credit": credited_stars_missing_purchase_credit,
    }
    await _send_payment_invariant_alerts(summary)
    logger.info("payment_invariant_alerts_finished", **summary)
    return summary


async def _send_payment_invariant_alerts(summary: dict[str, int]) -> None:
    if summary["precheckout_stuck"] > 0:
        await send_ops_alert(
            event="payments_precheckout_stuck_detected",
            payload={"precheckout_stuck": summary["precheckout_stuck"]},
        )
    if summary["paid_uncredited_stuck"] > 0:
        await send_ops_alert(
            event="payments_paid_uncredited_stuck_detected",
            payload={"paid_uncredited_stuck": summary["paid_uncredited_stuck"]},
        )
    credit_invariant_failures = (
        summary["credited_premium_missing_entitlement"]
        + summary["credited_stars_missing_purchase_credit"]
    )
    if credit_invariant_failures > 0:
        await send_ops_alert(
            event="payments_credit_invariant_failed",
            payload={
                "credit_invariant_failures": credit_invariant_failures,
                "credited_premium_missing_entitlement": summary[
                    "credited_premium_missing_entitlement"
                ],
                "credited_stars_missing_purchase_credit": summary[
                    "credited_stars_missing_purchase_credit"
                ],
            },
        )


async def run_telegram_stars_reconciliation_async() -> dict[str, object]:
    settings = get_settings()
    enabled = bool(getattr(settings, "telegram_stars_reconciliation_enabled", False))
    dry_run = bool(getattr(settings, "telegram_stars_reconciliation_dry_run", True))
    auto_recovery_enabled = bool(getattr(settings, "telegram_stars_auto_recovery_enabled", False))
    if not enabled:
        result: dict[str, object] = {
            "status": "disabled",
            "dry_run": dry_run,
            "auto_recovery_enabled": auto_recovery_enabled,
            "transactions_examined": 0,
        }
        logger.info("telegram_stars_reconciliation_skipped", **result)
        return result

    if not dry_run and not auto_recovery_enabled:
        result = {
            "status": "auto_recovery_disabled",
            "dry_run": dry_run,
            "auto_recovery_enabled": auto_recovery_enabled,
            "transactions_examined": 0,
        }
        logger.warning("telegram_stars_reconciliation_auto_recovery_disabled", **result)
        return result

    logger.info(
        "telegram_stars_reconciliation_started",
        dry_run=dry_run,
        auto_recovery_enabled=auto_recovery_enabled,
    )
    try:
        client = TelegramStarsClient(bot_token=settings.telegram_bot_token)
        transactions, pages_fetched, backlog_truncated = await _fetch_star_transactions_backlog(
            client
        )
    except TelegramStarsClientError as exc:
        result = {
            "status": "telegram_error",
            "dry_run": dry_run,
            "auto_recovery_enabled": auto_recovery_enabled,
            "transactions_examined": 0,
            "error_type": exc.error_type or type(exc).__name__,
        }
        logger.warning("telegram_stars_reconciliation_failed", **result)
        return result

    decisions: list[ReconciliationDecision] = []
    review_decisions: list[ReconciliationDecision] = []
    auto_recovery_counts: dict[str, int] = {}
    recovery_now_utc = _now_utc()
    async with SessionLocal() as session:
        for transaction in transactions:
            candidates = await _load_star_reconciliation_candidates(session, transaction)
            decision = classify_star_transaction_dry_run(
                transaction=transaction,
                candidates=candidates,
            )
            decisions.append(decision)
            if dry_run:
                if decision.severity in _REVIEWABLE_SEVERITIES:
                    review_decisions.append(decision)
                continue

            outcome = await _auto_recover_star_transaction_if_exact(
                transaction=transaction,
                decision=decision,
                recovery_now_utc=recovery_now_utc,
            )
            auto_recovery_counts[outcome] = auto_recovery_counts.get(outcome, 0) + 1
            if (
                outcome not in _AUTO_RECOVERY_SUCCESS_OUTCOMES
                and decision.severity in _REVIEWABLE_SEVERITIES
            ):
                review_decisions.append(decision)

    result = _build_telegram_stars_reconciliation_result(
        status="dry_run_completed" if dry_run else "auto_recovery_completed",
        decisions=decisions,
        dry_run=dry_run,
        auto_recovery_enabled=auto_recovery_enabled,
    )
    result["transactions_pages_fetched"] = pages_fetched
    result["transactions_backlog_truncated"] = backlog_truncated
    if auto_recovery_counts:
        result["auto_recovery_counts"] = auto_recovery_counts
        result["auto_recovered"] = auto_recovery_counts.get("auto_recovered", 0)
    review_summary = await _persist_telegram_stars_review_findings(review_decisions)
    result.update(review_summary)
    logger.info("telegram_stars_reconciliation_finished", **result)
    return result


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def _fetch_star_transactions_backlog(
    client: TelegramStarsClient,
) -> tuple[list[TelegramStarTransaction], int, bool]:
    transactions: list[TelegramStarTransaction] = []
    offset = 0
    pages_fetched = 0
    for _ in range(_TELEGRAM_STARS_RECONCILIATION_MAX_PAGES):
        page = await client.get_star_transactions(
            offset=offset,
            limit=_TELEGRAM_STARS_RECONCILIATION_PAGE_LIMIT,
        )
        pages_fetched += 1
        transactions.extend(page.transactions)
        page_size = len(page.transactions)
        if page_size < _TELEGRAM_STARS_RECONCILIATION_PAGE_LIMIT:
            return transactions, pages_fetched, False
        offset += page_size
    return transactions, pages_fetched, True


async def _load_star_reconciliation_candidates(
    session: AsyncSession,
    transaction: TelegramStarTransaction,
) -> list[ReconciliationCandidate]:
    rows = await _load_star_reconciliation_candidate_rows(
        session,
        transaction,
        for_update=False,
    )
    return _star_candidate_rows_to_reconciliation_candidates(rows)


async def _load_star_reconciliation_candidate_rows(
    session: AsyncSession,
    transaction: TelegramStarTransaction,
    *,
    for_update: bool,
) -> list[tuple[Purchase, int]]:
    if not transaction.is_incoming or transaction.transaction_type != "invoice_payment":
        return []
    return await PurchasesRepo.list_stars_reconciliation_candidate_rows(
        session,
        transaction_id=transaction.transaction_id,
        invoice_payload=transaction.invoice_payload,
        telegram_user_id=transaction.source_user_id,
        transaction_date=transaction.transaction_date,
        match_window=EXACT_MATCH_WINDOW,
        for_update=for_update,
    )


def _star_candidate_rows_to_reconciliation_candidates(
    rows: list[tuple[Purchase, int]],
) -> list[ReconciliationCandidate]:
    return [
        ReconciliationCandidate(
            purchase_id=purchase.id,
            user_id=purchase.user_id,
            telegram_user_id=telegram_user_id,
            stars_amount=purchase.stars_amount,
            status=purchase.status,
            created_at=purchase.created_at,
            telegram_payment_charge_id=purchase.telegram_payment_charge_id,
            invoice_payload=purchase.invoice_payload,
        )
        for purchase, telegram_user_id in rows
    ]


def _build_telegram_stars_reconciliation_result(
    *,
    status: str,
    decisions: list[ReconciliationDecision],
    dry_run: bool,
    auto_recovery_enabled: bool,
) -> dict[str, object]:
    classification_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    for decision in decisions:
        classification_counts[decision.classification] = (
            classification_counts.get(decision.classification, 0) + 1
        )
        severity_counts[decision.severity] = severity_counts.get(decision.severity, 0) + 1

    return {
        "status": status,
        "dry_run": dry_run,
        "auto_recovery_enabled": auto_recovery_enabled,
        "transactions_examined": len(decisions),
        "classification_counts": classification_counts,
        "severity_counts": severity_counts,
        "high_severity_findings": severity_counts.get("HIGH", 0),
        "medium_severity_findings": severity_counts.get("MEDIUM", 0),
    }


async def _auto_recover_star_transaction_if_exact(
    *,
    transaction: TelegramStarTransaction,
    decision: ReconciliationDecision,
    recovery_now_utc: datetime,
) -> str:
    if decision.classification == ALREADY_CREDITED:
        return "already_credited"
    if (
        decision.classification != WOULD_RECOVER_EXACT_MATCH
        or len(decision.candidate_purchase_ids) != 1
    ):
        return "not_exact_match"
    if transaction.invoice_payload is None:
        return "missing_invoice_payload"

    purchase_id = decision.candidate_purchase_ids[0]
    transaction_id_hash = _stable_payment_review_hash(transaction.transaction_id)
    async with SessionLocal.begin() as session:
        locked_rows = await _load_star_reconciliation_candidate_rows(
            session,
            transaction,
            for_update=True,
        )
        locked_candidates = _star_candidate_rows_to_reconciliation_candidates(locked_rows)
        locked_decision = classify_star_transaction_dry_run(
            transaction=transaction,
            candidates=locked_candidates,
        )
        if locked_decision.classification == ALREADY_CREDITED:
            return "already_credited"
        if (
            locked_decision.classification != WOULD_RECOVER_EXACT_MATCH
            or locked_decision.candidate_purchase_ids != (purchase_id,)
        ):
            return "revalidation_failed"

        purchase = _find_locked_purchase(locked_rows, purchase_id=purchase_id)
        if purchase is None:
            return "purchase_missing"
        if purchase.telegram_payment_charge_id not in (None, transaction.transaction_id):
            return "charge_conflict"

        open_review = await OutboxEventsRepo.get_open_by_payload_key(
            session,
            event_type=PAYMENT_STARS_RECONCILIATION_REVIEW_EVENT,
            payload_key="transaction_id_hash",
            payload_value=transaction_id_hash,
            status="OPEN",
        )
        if open_review is not None:
            return "open_review_blocked"

        if purchase.status not in {"PRECHECKOUT_OK", "INVOICE_SENT", "CREATED", "PAID_UNCREDITED"}:
            return "status_rejected"
        if purchase.invoice_payload != transaction.invoice_payload:
            return "invoice_payload_mismatch"

        charge_purchase = await PurchasesRepo.get_by_telegram_payment_charge_id_for_update(
            session,
            transaction.transaction_id,
        )
        if charge_purchase is not None and charge_purchase.id != purchase.id:
            return "charge_conflict"

        ledger_entry = await LedgerRepo.get_purchase_credit_for_update(
            session,
            purchase_id=purchase.id,
        )
        if ledger_entry is not None:
            return "ledger_conflict"

        product = get_product(purchase.product_code)
        if product is None:
            return "product_missing"
        if product.product_type == "PREMIUM":
            entitlement = await EntitlementsRepo.get_by_source_purchase_id_for_update(
                session,
                purchase_id=purchase.id,
                entitlement_type="PREMIUM",
            )
            if entitlement is not None:
                return "entitlement_conflict"

        await PurchaseService.apply_successful_payment(
            session,
            user_id=purchase.user_id,
            invoice_payload=transaction.invoice_payload,
            telegram_payment_charge_id=transaction.transaction_id,
            raw_successful_payment=_successful_payment_payload_from_star_transaction(transaction),
            now_utc=recovery_now_utc,
        )
        await OutboxEventsRepo.create(
            session,
            event_type=PAYMENT_STARS_AUTO_RECOVERED_EVENT,
            payload={
                "schema_version": 1,
                "source": "telegram_stars_reconciliation",
                "purchase_id": str(purchase.id),
                "transaction_id_hash": transaction_id_hash,
                "classification": decision.classification,
            },
            status="SENT",
        )
        logger.info(
            "telegram_stars_auto_recovery_finished",
            purchase_id=str(purchase.id),
            transaction_id_hash=transaction_id_hash,
            product_code=purchase.product_code,
        )
        return "auto_recovered"


def _find_locked_purchase(
    rows: list[tuple[Purchase, int]],
    *,
    purchase_id: UUID,
) -> Purchase | None:
    for purchase, _telegram_user_id in rows:
        if purchase.id == purchase_id:
            return purchase
    return None


def _successful_payment_payload_from_star_transaction(
    transaction: TelegramStarTransaction,
) -> dict[str, object]:
    return {
        "invoice_payload": transaction.invoice_payload,
        "currency": "XTR",
        "total_amount": transaction.amount,
        "telegram_payment_charge_id": transaction.transaction_id,
        "recovered_by": "telegram_stars_reconciliation",
        "transaction_date": transaction.transaction_date.isoformat(),
    }


async def _persist_telegram_stars_review_findings(
    decisions: list[ReconciliationDecision],
) -> dict[str, int]:
    review_decisions = [
        decision for decision in decisions if decision.severity in _REVIEWABLE_SEVERITIES
    ]
    if not review_decisions:
        return {"review_findings": 0, "review_events_created": 0, "review_events_existing": 0}

    created = 0
    existing = 0
    async with SessionLocal.begin() as session:
        for decision in review_decisions:
            _, was_created = await OutboxEventsRepo.create_once_by_payload_key(
                session,
                event_type=PAYMENT_STARS_RECONCILIATION_REVIEW_EVENT,
                payload=_telegram_stars_review_payload(decision),
                payload_key="review_key",
                status="OPEN",
            )
            if was_created:
                created += 1
            else:
                existing += 1

    return {
        "review_findings": len(review_decisions),
        "review_events_created": created,
        "review_events_existing": existing,
    }


def _telegram_stars_review_payload(decision: ReconciliationDecision) -> dict[str, object]:
    candidate_purchase_ids = [str(purchase_id) for purchase_id in decision.candidate_purchase_ids]
    return {
        "schema_version": 1,
        "source": "telegram_stars_reconciliation",
        "reason": decision.classification,
        "severity": decision.severity,
        "review_key": _stable_payment_review_hash(
            f"{decision.transaction_id}:{decision.classification}"
        ),
        "transaction_id_hash": _stable_payment_review_hash(decision.transaction_id),
        "candidate_purchase_ids": candidate_purchase_ids,
        "candidate_purchase_count": len(candidate_purchase_ids),
        "raw_payload_stored": False,
    }


def _stable_payment_review_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
