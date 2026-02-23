from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.ledger_entries import LedgerEntry
from app.db.models.purchases import Purchase
from app.db.models.reconciliation_runs import ReconciliationRun
from app.db.session import SessionLocal
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
                base_stars_amount=5,
                discount_stars_amount=0,
                stars_amount=5,
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
