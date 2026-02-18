from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.models.ledger_entries import LedgerEntry
from app.db.models.purchases import Purchase
from app.db.models.reconciliation_runs import ReconciliationRun
from app.db.repo.energy_repo import EnergyRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.purchases.errors import StreakSaverPurchaseLimitError
from app.economy.purchases.recovery import RECOVERY_FAILURES_KEY
from app.economy.purchases.service import PurchaseService
from app.workers.tasks.payments_reliability import (
    expire_stale_unpaid_invoices_async,
    recover_paid_uncredited_async,
    run_payments_reconciliation_async,
)

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=10_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="Integration",
            referred_by_user_id=None,
        )
        return user.id


@pytest.mark.asyncio
async def test_duplicate_payment_callbacks_credit_only_once() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user("duplicate-callbacks")

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="buy:dup:integration:1",
            now_utc=now_utc,
        )
        await PurchaseService.mark_invoice_sent(session, purchase_id=init.purchase_id)
        await PurchaseService.validate_precheckout(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            total_amount=10,
        )
        await PurchaseService.validate_precheckout(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            total_amount=10,
        )

        first = await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_dup_001",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc,
        )
        second = await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_dup_001",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc,
        )
        third = await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_dup_001",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc,
        )

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert third.idempotent_replay is True

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, init.purchase_id)
        assert purchase is not None
        assert purchase.status == "CREDITED"

        energy_state = await EnergyRepo.get_by_user_id(session, user_id)
        assert energy_state is not None
        assert energy_state.paid_energy == 10

        count_stmt = select(func.count(LedgerEntry.id)).where(
            LedgerEntry.idempotency_key == f"credit:energy:{init.purchase_id}",
        )
        credit_entries_count = await session.scalar(count_stmt)
        assert credit_entries_count == 1


@pytest.mark.asyncio
async def test_init_purchase_reuses_active_invoice_for_same_user_product() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user("active-invoice-lock")

    async with SessionLocal.begin() as session:
        first = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="buy:active-lock:1",
            now_utc=now_utc,
        )
        await PurchaseService.mark_invoice_sent(session, purchase_id=first.purchase_id)

    async with SessionLocal.begin() as session:
        second = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="buy:active-lock:2",
            now_utc=now_utc + timedelta(seconds=1),
        )

    assert second.idempotent_replay is True
    assert second.purchase_id == first.purchase_id
    assert second.invoice_payload == first.invoice_payload

    async with SessionLocal.begin() as session:
        count_stmt = select(func.count(Purchase.id)).where(
            Purchase.user_id == user_id,
            Purchase.product_code == "ENERGY_10",
        )
        purchase_count = await session.scalar(count_stmt)
        assert purchase_count == 1


@pytest.mark.asyncio
async def test_streak_saver_is_blocked_within_7_day_window() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user("streak-saver-limit")

    async with SessionLocal.begin() as session:
        first = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="STREAK_SAVER_20",
            idempotency_key="buy:streak-saver:1",
            now_utc=now_utc,
        )
        await PurchaseService.mark_invoice_sent(session, purchase_id=first.purchase_id)
        await PurchaseService.validate_precheckout(
            session,
            user_id=user_id,
            invoice_payload=first.invoice_payload,
            total_amount=20,
            now_utc=now_utc,
        )
        await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=first.invoice_payload,
            telegram_payment_charge_id="tg_charge_streak_saver_1",
            raw_successful_payment={"invoice_payload": first.invoice_payload},
            now_utc=now_utc,
        )

    with pytest.raises(StreakSaverPurchaseLimitError):
        async with SessionLocal.begin() as session:
            await PurchaseService.init_purchase(
                session,
                user_id=user_id,
                product_code="STREAK_SAVER_20",
                idempotency_key="buy:streak-saver:2",
                now_utc=now_utc + timedelta(days=6, hours=23),
            )

    async with SessionLocal.begin() as session:
        count_stmt = select(func.count(Purchase.id)).where(
            Purchase.user_id == user_id,
            Purchase.product_code == "STREAK_SAVER_20",
        )
        purchase_count = await session.scalar(count_stmt)
        assert purchase_count == 1


@pytest.mark.asyncio
async def test_streak_saver_is_allowed_after_7_days() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user("streak-saver-allowed")

    async with SessionLocal.begin() as session:
        first = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="STREAK_SAVER_20",
            idempotency_key="buy:streak-saver:3",
            now_utc=now_utc,
        )
        await PurchaseService.mark_invoice_sent(session, purchase_id=first.purchase_id)
        await PurchaseService.validate_precheckout(
            session,
            user_id=user_id,
            invoice_payload=first.invoice_payload,
            total_amount=20,
            now_utc=now_utc,
        )
        await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=first.invoice_payload,
            telegram_payment_charge_id="tg_charge_streak_saver_2",
            raw_successful_payment={"invoice_payload": first.invoice_payload},
            now_utc=now_utc,
        )

    async with SessionLocal.begin() as session:
        second = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="STREAK_SAVER_20",
            idempotency_key="buy:streak-saver:4",
            now_utc=now_utc + timedelta(days=7),
        )
        assert second.idempotent_replay is False
        assert second.purchase_id != first.purchase_id

    async with SessionLocal.begin() as session:
        count_stmt = select(func.count(Purchase.id)).where(
            Purchase.user_id == user_id,
            Purchase.product_code == "STREAK_SAVER_20",
        )
        purchase_count = await session.scalar(count_stmt)
        assert purchase_count == 2


@pytest.mark.asyncio
async def test_recovery_job_credits_stale_paid_uncredited_purchase() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("recovery-success")
    purchase_id = uuid4()

    async with SessionLocal.begin() as session:
        session.add(
            Purchase(
                id=purchase_id,
                user_id=user_id,
                product_code="ENERGY_10",
                product_type="MICRO",
                base_stars_amount=10,
                discount_stars_amount=0,
                stars_amount=10,
                currency="XTR",
                status="PAID_UNCREDITED",
                idempotency_key="recovery-success-1",
                invoice_payload="inv_recovery_success_1",
                telegram_payment_charge_id="tg_charge_recovery_1",
                raw_successful_payment={"invoice_payload": "inv_recovery_success_1"},
                created_at=now_utc - timedelta(minutes=15),
                paid_at=now_utc - timedelta(minutes=10),
            )
        )
        await session.flush()

    result = await recover_paid_uncredited_async(batch_size=50, stale_minutes=2)
    assert result["examined"] == 1
    assert result["credited"] == 1

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, purchase_id)
        assert purchase is not None
        assert purchase.status == "CREDITED"
        assert purchase.credited_at is not None

        energy_state = await EnergyRepo.get_by_user_id(session, user_id)
        assert energy_state is not None
        assert energy_state.paid_energy == 10


@pytest.mark.asyncio
async def test_recovery_marks_purchase_for_review_after_three_failures() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("recovery-review")
    purchase_id = uuid4()

    async with SessionLocal.begin() as session:
        session.add(
            Purchase(
                id=purchase_id,
                user_id=user_id,
                product_code="UNKNOWN_PRODUCT",
                product_type="MICRO",
                base_stars_amount=1,
                discount_stars_amount=0,
                stars_amount=1,
                currency="XTR",
                status="PAID_UNCREDITED",
                idempotency_key="recovery-review-1",
                invoice_payload="inv_recovery_review_1",
                telegram_payment_charge_id="tg_charge_recovery_review_1",
                raw_successful_payment={"invoice_payload": "inv_recovery_review_1"},
                created_at=now_utc - timedelta(minutes=15),
                paid_at=now_utc - timedelta(minutes=10),
            )
        )
        await session.flush()

    first = await recover_paid_uncredited_async(batch_size=50, stale_minutes=2)
    second = await recover_paid_uncredited_async(batch_size=50, stale_minutes=2)
    third = await recover_paid_uncredited_async(batch_size=50, stale_minutes=2)

    assert first["retryable_failure"] == 1
    assert second["retryable_failure"] == 1
    assert third["review"] == 1

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, purchase_id)
        assert purchase is not None
        assert purchase.status == "FAILED_CREDIT_PENDING_REVIEW"
        assert isinstance(purchase.raw_successful_payment, dict)
        assert purchase.raw_successful_payment[RECOVERY_FAILURES_KEY] == 3


@pytest.mark.asyncio
async def test_expire_stale_unpaid_invoices_marks_created_and_invoice_sent_as_failed() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("stale-unpaid-invoices")

    created_old_id = uuid4()
    invoice_sent_old_id = uuid4()
    created_recent_id = uuid4()

    async with SessionLocal.begin() as session:
        session.add(
            Purchase(
                id=created_old_id,
                user_id=user_id,
                product_code="ENERGY_10",
                product_type="MICRO",
                base_stars_amount=10,
                discount_stars_amount=0,
                stars_amount=10,
                currency="XTR",
                status="CREATED",
                idempotency_key="stale-created-old-1",
                invoice_payload="inv_stale_created_old_1",
                created_at=now_utc - timedelta(minutes=45),
            )
        )
        session.add(
            Purchase(
                id=invoice_sent_old_id,
                user_id=user_id,
                product_code="MEGA_PACK_15",
                product_type="MICRO",
                base_stars_amount=15,
                discount_stars_amount=0,
                stars_amount=15,
                currency="XTR",
                status="INVOICE_SENT",
                idempotency_key="stale-invoice-old-1",
                invoice_payload="inv_stale_invoice_old_1",
                created_at=now_utc - timedelta(minutes=44),
            )
        )
        session.add(
            Purchase(
                id=created_recent_id,
                user_id=user_id,
                product_code="STREAK_SAVER_20",
                product_type="MICRO",
                base_stars_amount=20,
                discount_stars_amount=0,
                stars_amount=20,
                currency="XTR",
                status="CREATED",
                idempotency_key="stale-created-recent-1",
                invoice_payload="inv_stale_created_recent_1",
                created_at=now_utc - timedelta(minutes=10),
            )
        )
        await session.flush()

    result = await expire_stale_unpaid_invoices_async(stale_minutes=30)
    assert result["expired_invoices"] == 2

    async with SessionLocal.begin() as session:
        created_old = await PurchasesRepo.get_by_id(session, created_old_id)
        invoice_sent_old = await PurchasesRepo.get_by_id(session, invoice_sent_old_id)
        created_recent = await PurchasesRepo.get_by_id(session, created_recent_id)

        assert created_old is not None and created_old.status == "FAILED"
        assert invoice_sent_old is not None and invoice_sent_old.status == "FAILED"
        assert created_recent is not None and created_recent.status == "CREATED"


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
                base_stars_amount=10,
                discount_stars_amount=0,
                stars_amount=10,
                currency="XTR",
                status="CREDITED",
                idempotency_key="recon-credited-1",
                invoice_payload="inv_recon_credited_1",
                telegram_payment_charge_id="tg_charge_recon_credited_1",
                raw_successful_payment={"invoice_payload": "inv_recon_credited_1"},
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
                base_stars_amount=10,
                discount_stars_amount=0,
                stars_amount=10,
                currency="XTR",
                status="PAID_UNCREDITED",
                idempotency_key="recon-stale-1",
                invoice_payload="inv_recon_stale_1",
                telegram_payment_charge_id="tg_charge_recon_stale_1",
                raw_successful_payment={"invoice_payload": "inv_recon_stale_1"},
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
    assert result["paid_stars_total"] == 20
    assert result["credited_stars_total"] == 10
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
