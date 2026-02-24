from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.session import SessionLocal
from app.economy.purchases.service import PurchaseService
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_credited_purchase_refund_creates_single_debit_and_revokes_entitlements() -> None:
    created_at = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    refunded_at = created_at + timedelta(hours=1)
    user_id = await _create_user("refund-premium-credit")

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="PREMIUM_MONTH",
            idempotency_key="refund-premium-credit:init",
            now_utc=created_at,
        )
        await PurchaseService.mark_invoice_sent(session, purchase_id=init.purchase_id)
        await PurchaseService.validate_precheckout(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            total_amount=init.final_stars_amount,
            now_utc=created_at,
        )
        await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_refund_credit_1",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=created_at,
        )

    async with SessionLocal.begin() as session:
        first_refund = await PurchaseService.refund_purchase(
            session,
            purchase_id=init.purchase_id,
            now_utc=refunded_at,
        )
        second_refund = await PurchaseService.refund_purchase(
            session,
            purchase_id=init.purchase_id,
            now_utc=refunded_at + timedelta(minutes=1),
        )

    assert first_refund.idempotent_replay is False
    assert second_refund.idempotent_replay is True

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, init.purchase_id)
        assert purchase is not None
        assert purchase.status == "REFUNDED"
        assert purchase.refunded_at is not None

        credit_entries_stmt = select(func.count(LedgerEntry.id)).where(
            LedgerEntry.purchase_id == init.purchase_id,
            LedgerEntry.entry_type == "PURCHASE_CREDIT",
            LedgerEntry.direction == "CREDIT",
        )
        debit_entries_stmt = select(func.count(LedgerEntry.id)).where(
            LedgerEntry.purchase_id == init.purchase_id,
            LedgerEntry.entry_type == "PURCHASE_REFUND",
            LedgerEntry.direction == "DEBIT",
        )
        assert int((await session.scalar(credit_entries_stmt)) or 0) == 1
        assert int((await session.scalar(debit_entries_stmt)) or 0) == 1

        credit_entry = await session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.purchase_id == init.purchase_id,
                LedgerEntry.entry_type == "PURCHASE_CREDIT",
                LedgerEntry.direction == "CREDIT",
            )
        )
        debit_entry = await session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.purchase_id == init.purchase_id,
                LedgerEntry.entry_type == "PURCHASE_REFUND",
                LedgerEntry.direction == "DEBIT",
            )
        )
        assert credit_entry is not None
        assert debit_entry is not None
        assert debit_entry.amount == credit_entry.amount
        assert debit_entry.idempotency_key == f"refund:{init.purchase_id}"

        active_entitlements = await session.scalar(
            select(func.count(Entitlement.id)).where(
                Entitlement.source_purchase_id == init.purchase_id,
                Entitlement.status.in_(("ACTIVE", "SCHEDULED")),
            )
        )
        revoked_entitlements = await session.scalar(
            select(func.count(Entitlement.id)).where(
                Entitlement.source_purchase_id == init.purchase_id,
                Entitlement.status == "REVOKED",
            )
        )
        assert int(active_entitlements or 0) == 0
        assert int(revoked_entitlements or 0) >= 1
