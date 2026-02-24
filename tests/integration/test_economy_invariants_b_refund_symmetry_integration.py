from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.models.mode_access import ModeAccess
from app.db.models.purchases import Purchase
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.session import SessionLocal
from app.economy.purchases.catalog import MEGA_PACK_MODE_CODES
from app.economy.purchases.errors import PurchaseRefundValidationError
from app.economy.purchases.service import PurchaseService
from app.workers.tasks.payments_reliability import recover_paid_uncredited_async
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


async def _create_credited_purchase(
    *,
    user_id: int,
    product_code: str,
    idempotency_prefix: str,
    now_utc: datetime,
) -> UUID:
    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code=product_code,
            idempotency_key=f"{idempotency_prefix}:init",
            now_utc=now_utc,
        )
        await PurchaseService.mark_invoice_sent(session, purchase_id=init.purchase_id)
        await PurchaseService.validate_precheckout(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            total_amount=init.final_stars_amount,
            now_utc=now_utc,
        )
        credit_result = await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id=f"tg_charge_{idempotency_prefix}",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc,
        )
        assert credit_result.idempotent_replay is False
        return init.purchase_id


@pytest.mark.asyncio
async def test_refund_creates_single_debit_and_marks_refunded() -> None:
    created_at = datetime(2026, 2, 18, 13, 0, tzinfo=UTC)
    refunded_at = created_at + timedelta(hours=1)
    user_id = await _create_user("inv-b-refund-single-debit")
    purchase_id = await _create_credited_purchase(
        user_id=user_id,
        product_code="PREMIUM_MONTH",
        idempotency_prefix="inv-b-refund-single-debit",
        now_utc=created_at,
    )

    async with SessionLocal.begin() as session:
        result = await PurchaseService.refund_purchase(
            session,
            purchase_id=purchase_id,
            now_utc=refunded_at,
        )
    assert result.idempotent_replay is False

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, purchase_id)
        assert purchase is not None
        assert purchase.status == "REFUNDED"
        assert purchase.refunded_at is not None

        debit_count = await session.scalar(
            select(func.count(LedgerEntry.id)).where(
                LedgerEntry.purchase_id == purchase_id,
                LedgerEntry.entry_type == "PURCHASE_REFUND",
                LedgerEntry.direction == "DEBIT",
            )
        )
        assert int(debit_count or 0) == 1

        debit_entry = await session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.purchase_id == purchase_id,
                LedgerEntry.entry_type == "PURCHASE_REFUND",
                LedgerEntry.direction == "DEBIT",
            )
        )
        assert debit_entry is not None
        assert debit_entry.idempotency_key == f"refund:{purchase_id}"


@pytest.mark.asyncio
async def test_refund_is_idempotent_without_duplicate_debits() -> None:
    created_at = datetime(2026, 2, 18, 13, 15, tzinfo=UTC)
    user_id = await _create_user("inv-b-refund-idempotent")
    purchase_id = await _create_credited_purchase(
        user_id=user_id,
        product_code="ENERGY_10",
        idempotency_prefix="inv-b-refund-idempotent",
        now_utc=created_at,
    )

    async with SessionLocal.begin() as session:
        first = await PurchaseService.refund_purchase(
            session,
            purchase_id=purchase_id,
            now_utc=created_at + timedelta(hours=1),
        )
        second = await PurchaseService.refund_purchase(
            session,
            purchase_id=purchase_id,
            now_utc=created_at + timedelta(hours=1, minutes=1),
        )

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True

    async with SessionLocal.begin() as session:
        debit_count = await session.scalar(
            select(func.count(LedgerEntry.id)).where(
                LedgerEntry.purchase_id == purchase_id,
                LedgerEntry.entry_type == "PURCHASE_REFUND",
                LedgerEntry.direction == "DEBIT",
            )
        )
        assert int(debit_count or 0) == 1


@pytest.mark.asyncio
async def test_refund_revokes_entitlements_for_source_purchase() -> None:
    created_at = datetime(2026, 2, 18, 13, 30, tzinfo=UTC)
    refunded_at = created_at + timedelta(hours=1)
    user_id = await _create_user("inv-b-refund-entitlements")
    purchase_id = await _create_credited_purchase(
        user_id=user_id,
        product_code="PREMIUM_MONTH",
        idempotency_prefix="inv-b-refund-entitlements",
        now_utc=created_at,
    )

    async with SessionLocal.begin() as session:
        active_before = await session.scalar(
            select(func.count(Entitlement.id)).where(
                Entitlement.source_purchase_id == purchase_id,
                Entitlement.status.in_(("ACTIVE", "SCHEDULED")),
            )
        )
    assert int(active_before or 0) >= 1

    async with SessionLocal.begin() as session:
        await PurchaseService.refund_purchase(
            session,
            purchase_id=purchase_id,
            now_utc=refunded_at,
        )

    async with SessionLocal.begin() as session:
        active_after = await session.scalar(
            select(func.count(Entitlement.id)).where(
                Entitlement.source_purchase_id == purchase_id,
                Entitlement.status.in_(("ACTIVE", "SCHEDULED")),
            )
        )
        revoked_after = await session.scalar(
            select(func.count(Entitlement.id)).where(
                Entitlement.source_purchase_id == purchase_id,
                Entitlement.status == "REVOKED",
            )
        )
        assert int(active_after or 0) == 0
        assert int(revoked_after or 0) >= 1


@pytest.mark.asyncio
async def test_refund_revokes_mode_access_for_source_purchase() -> None:
    created_at = datetime(2026, 2, 18, 13, 45, tzinfo=UTC)
    refunded_at = created_at + timedelta(hours=1)
    user_id = await _create_user("inv-b-refund-mode-access")
    purchase_id = await _create_credited_purchase(
        user_id=user_id,
        product_code="MEGA_PACK_15",
        idempotency_prefix="inv-b-refund-mode-access",
        now_utc=created_at,
    )

    async with SessionLocal.begin() as session:
        active_before = await session.scalar(
            select(func.count(ModeAccess.id)).where(
                ModeAccess.source_purchase_id == purchase_id,
                ModeAccess.status == "ACTIVE",
            )
        )
    assert int(active_before or 0) == len(MEGA_PACK_MODE_CODES)

    async with SessionLocal.begin() as session:
        await PurchaseService.refund_purchase(
            session,
            purchase_id=purchase_id,
            now_utc=refunded_at,
        )

    async with SessionLocal.begin() as session:
        rows = list(
            (
                await session.execute(
                    select(ModeAccess.status, ModeAccess.ends_at).where(
                        ModeAccess.source_purchase_id == purchase_id
                    )
                )
            ).all()
        )
        assert len(rows) == len(MEGA_PACK_MODE_CODES)
        assert all(status == "REVOKED" for status, _ in rows)
        assert all(ends_at is not None and ends_at <= refunded_at for _, ends_at in rows)


@pytest.mark.asyncio
async def test_refund_requires_credited_purchase() -> None:
    now_utc = datetime(2026, 2, 18, 14, 0, tzinfo=UTC)
    user_id = await _create_user("inv-b-refund-requires-credited")

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="inv-b-refund-requires-credited:init",
            now_utc=now_utc,
        )

    with pytest.raises(PurchaseRefundValidationError):
        async with SessionLocal.begin() as session:
            await PurchaseService.refund_purchase(
                session,
                purchase_id=init.purchase_id,
                now_utc=now_utc + timedelta(minutes=5),
            )

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, init.purchase_id)
        assert purchase is not None
        assert purchase.status == "CREATED"

        debit_count = await session.scalar(
            select(func.count(LedgerEntry.id)).where(
                LedgerEntry.purchase_id == init.purchase_id,
                LedgerEntry.entry_type == "PURCHASE_REFUND",
                LedgerEntry.direction == "DEBIT",
            )
        )
        assert int(debit_count or 0) == 0


@pytest.mark.asyncio
async def test_refund_after_recovery_keeps_single_credit_and_single_debit() -> None:
    now_utc = datetime(2026, 2, 18, 14, 15, tzinfo=UTC)
    purchase_id = uuid4()
    user_id = await _create_user("inv-b-refund-after-recovery")

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
                idempotency_key="inv-b-refund-after-recovery:init",
                invoice_payload="inv_b_refund_after_recovery_1",
                telegram_payment_charge_id="tg_charge_inv_b_refund_after_recovery_1",
                raw_successful_payment={"invoice_payload": "inv_b_refund_after_recovery_1"},
                created_at=now_utc - timedelta(minutes=20),
                paid_at=now_utc - timedelta(minutes=10),
            )
        )

    first_recovery = await recover_paid_uncredited_async(batch_size=10, stale_minutes=1)
    second_recovery = await recover_paid_uncredited_async(batch_size=10, stale_minutes=1)
    assert first_recovery["credited"] == 1
    assert second_recovery["credited"] == 0

    async with SessionLocal.begin() as session:
        await PurchaseService.refund_purchase(
            session,
            purchase_id=purchase_id,
            now_utc=now_utc + timedelta(hours=1),
        )

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, purchase_id)
        assert purchase is not None
        assert purchase.status == "REFUNDED"

        credit_count = await session.scalar(
            select(func.count(LedgerEntry.id)).where(
                LedgerEntry.purchase_id == purchase_id,
                LedgerEntry.entry_type == "PURCHASE_CREDIT",
                LedgerEntry.direction == "CREDIT",
            )
        )
        debit_count = await session.scalar(
            select(func.count(LedgerEntry.id)).where(
                LedgerEntry.purchase_id == purchase_id,
                LedgerEntry.entry_type == "PURCHASE_REFUND",
                LedgerEntry.direction == "DEBIT",
            )
        )
        assert int(credit_count or 0) == 1
        assert int(debit_count or 0) == 1
