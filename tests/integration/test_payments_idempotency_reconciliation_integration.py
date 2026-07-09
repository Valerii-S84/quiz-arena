from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.ledger_entries import LedgerEntry
from app.db.models.purchases import Purchase
from app.db.models.reconciliation_runs import ReconciliationRun
from app.db.models.users import User
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.session import SessionLocal
from app.services.payment_reconciliation import (
    WOULD_RECOVER_EXACT_MATCH,
    ReconciliationCandidate,
    classify_star_transaction_dry_run,
)
from app.services.telegram_stars import TelegramStarTransaction
from app.workers.tasks.payments_reliability import run_payments_reconciliation_async
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_reconciliation_detects_diff_and_persists_run() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("reconciliation")

    credited_purchase_id = uuid4()
    stale_paid_uncredited_id = uuid4()

    async with SessionLocal.begin() as session:
        session.add(
            Purchase(
                id=credited_purchase_id,
                user_id=user_id,
                product_code="ENERGY_10",
                product_type="MICRO",
                base_stars_amount=5,
                discount_stars_amount=0,
                stars_amount=5,
                currency="XTR",
                status="CREDITED",
                idempotency_key="recon-credited-1",
                invoice_payload="inv_recon_credited_1",
                telegram_payment_charge_id="tg_charge_recon_credited_1",
                raw_successful_payment={
                    "invoice_payload": "inv_recon_credited_1",
                    "currency": "XTR",
                    "total_amount": 5,
                },
                created_at=now_utc - timedelta(minutes=50),
                paid_at=now_utc - timedelta(minutes=45),
                credited_at=now_utc - timedelta(minutes=44),
            )
        )
        session.add(
            Purchase(
                id=stale_paid_uncredited_id,
                user_id=user_id,
                product_code="ENERGY_10",
                product_type="MICRO",
                base_stars_amount=5,
                discount_stars_amount=0,
                stars_amount=5,
                currency="XTR",
                status="PAID_UNCREDITED",
                idempotency_key="recon-stale-1",
                invoice_payload="inv_recon_stale_1",
                telegram_payment_charge_id="tg_charge_recon_stale_1",
                raw_successful_payment={
                    "invoice_payload": "inv_recon_stale_1",
                    "currency": "XTR",
                    "total_amount": 5,
                },
                created_at=now_utc - timedelta(minutes=50),
                paid_at=now_utc - timedelta(minutes=45),
            )
        )
        await session.flush()

        session.add(
            LedgerEntry(
                user_id=user_id,
                purchase_id=credited_purchase_id,
                entry_type="PURCHASE_CREDIT",
                asset="PAID_ENERGY",
                direction="CREDIT",
                amount=10,
                balance_after=10,
                source="PURCHASE",
                idempotency_key="ledger-recon-credited-1",
                metadata_={},
                created_at=now_utc - timedelta(minutes=44),
            )
        )
        await session.flush()

    result = await run_payments_reconciliation_async(stale_minutes=30)
    assert result["paid_purchases_count"] == 2
    assert result["credited_purchases_count"] == 1
    assert result["stale_paid_uncredited_count"] == 1
    assert result["paid_stars_total"] == 10
    assert result["credited_stars_total"] == 5
    assert result["product_stars_mismatch_count"] == 1
    assert result["diff_count"] == 4
    assert result["status"] == "DIFF"

    async with SessionLocal.begin() as session:
        run_stmt = select(ReconciliationRun).order_by(ReconciliationRun.id.desc()).limit(1)
        latest_run = await session.scalar(run_stmt)
        assert latest_run is not None
        assert latest_run.status == "DIFF"
        assert latest_run.diff_count == 4
        assert latest_run.finished_at is not None


@pytest.mark.asyncio
async def test_reconciliation_ignores_refund_only_purchase_but_counts_refunded_credit() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("reconciliation-refund-only")
    refunded_credit_id = uuid4()
    refund_only_id = uuid4()

    async with SessionLocal.begin() as session:
        session.add(
            Purchase(
                id=refunded_credit_id,
                user_id=user_id,
                product_code="ENERGY_10",
                product_type="MICRO",
                base_stars_amount=5,
                discount_stars_amount=0,
                stars_amount=5,
                currency="XTR",
                status="REFUNDED",
                idempotency_key="recon-refunded-credit-1",
                invoice_payload="inv_recon_refunded_credit_1",
                telegram_payment_charge_id="tg_charge_recon_refunded_credit_1",
                raw_successful_payment={"invoice_payload": "inv_recon_refunded_credit_1"},
                created_at=now_utc - timedelta(minutes=50),
                paid_at=now_utc - timedelta(minutes=45),
                credited_at=now_utc - timedelta(minutes=44),
                refunded_at=now_utc - timedelta(minutes=40),
            )
        )
        session.add(
            Purchase(
                id=refund_only_id,
                user_id=user_id,
                product_code="ENERGY_10",
                product_type="MICRO",
                base_stars_amount=5,
                discount_stars_amount=0,
                stars_amount=5,
                currency="XTR",
                status="REFUNDED",
                idempotency_key="recon-refund-only-1",
                invoice_payload="inv_recon_refund_only_1",
                telegram_payment_charge_id="tg_charge_recon_refund_only_1",
                raw_successful_payment=None,
                created_at=now_utc - timedelta(minutes=50),
                paid_at=now_utc - timedelta(minutes=45),
                credited_at=None,
                refunded_at=now_utc - timedelta(minutes=40),
            )
        )
        await session.flush()
        session.add(
            LedgerEntry(
                user_id=user_id,
                purchase_id=refunded_credit_id,
                entry_type="PURCHASE_CREDIT",
                asset="PAID_ENERGY",
                direction="CREDIT",
                amount=10,
                balance_after=10,
                source="PURCHASE",
                idempotency_key="ledger-recon-refunded-credit-1",
                metadata_={},
                created_at=now_utc - timedelta(minutes=44),
            )
        )
        await session.flush()

    result = await run_payments_reconciliation_async(stale_minutes=30)

    assert result["paid_purchases_count"] == 1
    assert result["credited_purchases_count"] == 1
    assert result["paid_stars_total"] == 5
    assert result["credited_stars_total"] == 5
    assert result["product_stars_mismatch_count"] == 0
    assert result["diff_count"] == 0
    assert result["status"] == "OK"


@pytest.mark.asyncio
async def test_stars_candidate_query_keeps_older_exact_match_before_fuzzy_limit() -> None:
    now_utc = datetime.now(UTC)
    transaction_date = now_utc
    user_id = await _create_user("reconciliation-exact-before-fuzzy-limit")
    exact_purchase_id = uuid4()

    async with SessionLocal.begin() as session:
        telegram_user_id = await session.scalar(
            select(User.telegram_user_id).where(User.id == user_id)
        )
        assert telegram_user_id is not None
        session.add(
            Purchase(
                id=exact_purchase_id,
                user_id=user_id,
                product_code="ENERGY_10",
                product_type="MICRO",
                base_stars_amount=29,
                discount_stars_amount=0,
                stars_amount=29,
                currency="XTR",
                status="PRECHECKOUT_OK",
                idempotency_key="recon-exact-before-fuzzy",
                invoice_payload="inv_recon_exact_before_fuzzy",
                telegram_payment_charge_id="tg_charge_recon_exact_before_fuzzy",
                created_at=transaction_date - timedelta(minutes=20),
            )
        )
        for index in range(5):
            session.add(
                Purchase(
                    id=uuid4(),
                    user_id=user_id,
                    product_code=f"FUZZY_{index}",
                    product_type="MICRO",
                    base_stars_amount=99,
                    discount_stars_amount=0,
                    stars_amount=99,
                    currency="XTR",
                    status="CREATED",
                    idempotency_key=f"recon-fuzzy-newer-{index}",
                    invoice_payload=f"inv_recon_fuzzy_newer_{index}",
                    telegram_payment_charge_id=None,
                    created_at=transaction_date - timedelta(minutes=index + 1),
                )
            )
        await session.flush()

    transaction = TelegramStarTransaction(
        transaction_id="tg_charge_recon_exact_before_fuzzy",
        amount=29,
        transaction_date=transaction_date,
        source={
            "type": "user",
            "transaction_type": "invoice_payment",
            "user": {"id": telegram_user_id},
            "invoice_payload": "inv_recon_exact_before_fuzzy",
        },
        receiver=None,
        raw_payload={},
    )
    async with SessionLocal.begin() as session:
        rows = await PurchasesRepo.list_stars_reconciliation_candidate_rows(
            session,
            transaction_id=transaction.transaction_id,
            invoice_payload=transaction.invoice_payload,
            telegram_user_id=transaction.partner_user_id,
            transaction_date=transaction.transaction_date,
            match_window=timedelta(minutes=30),
            limit=3,
        )

    assert exact_purchase_id in {purchase.id for purchase, _ in rows}
    decision = classify_star_transaction_dry_run(
        transaction=transaction,
        candidates=[
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
        ],
    )

    assert decision.classification == WOULD_RECOVER_EXACT_MATCH
    assert decision.candidate_purchase_ids == (exact_purchase_id,)
