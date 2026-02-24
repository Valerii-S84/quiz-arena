from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.models.ledger_entries import LedgerEntry
from app.db.models.purchases import Purchase
from app.db.repo.energy_repo import EnergyRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.session import SessionLocal
from app.economy.purchases.service import PurchaseService
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


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
            total_amount=5,
        )
        await PurchaseService.validate_precheckout(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            total_amount=5,
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
            LedgerEntry.idempotency_key == f"credit:purchase:{init.purchase_id}",
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
