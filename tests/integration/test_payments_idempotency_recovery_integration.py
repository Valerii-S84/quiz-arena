from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.db.models.purchases import Purchase
from app.db.repo.energy_repo import EnergyRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.session import SessionLocal
from app.economy.purchases.recovery import RECOVERY_FAILURES_KEY
from app.workers.tasks.payments_reliability import (
    expire_stale_unpaid_invoices_async,
    recover_paid_uncredited_async,
)
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


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
                base_stars_amount=5,
                discount_stars_amount=0,
                stars_amount=5,
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
                base_stars_amount=5,
                discount_stars_amount=0,
                stars_amount=5,
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
