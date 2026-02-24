from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.db.models.energy_state import EnergyState
from app.db.models.ledger_entries import LedgerEntry
from app.db.repo.energy_repo import EnergyRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.session import SessionLocal
from app.economy.energy.time import berlin_local_date
from app.economy.purchases.catalog import MEGA_PACK_MODE_CODES
from app.economy.purchases.service import PurchaseService
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


async def _create_credited_purchase(
    *,
    user_id: int,
    product_code: str,
    idempotency_prefix: str,
    now_utc: datetime,
) -> tuple[UUID, int]:
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
        return init.purchase_id, init.final_stars_amount


@pytest.mark.asyncio
async def test_credit_creates_single_ledger_entry_per_purchase() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user("inv-a-credit-single-entry")
    purchase_id, final_stars_amount = await _create_credited_purchase(
        user_id=user_id,
        product_code="MEGA_PACK_15",
        idempotency_prefix="inv-a-credit-single-entry",
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        count_stmt = select(func.count(LedgerEntry.id)).where(
            LedgerEntry.purchase_id == purchase_id,
            LedgerEntry.entry_type == "PURCHASE_CREDIT",
            LedgerEntry.direction == "CREDIT",
        )
        entry_count = await session.scalar(count_stmt)
        assert int(entry_count or 0) == 1

        entry = await session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.purchase_id == purchase_id,
                LedgerEntry.entry_type == "PURCHASE_CREDIT",
                LedgerEntry.direction == "CREDIT",
            )
        )
        assert entry is not None
        assert entry.amount == final_stars_amount
        assert entry.metadata_["product_code"] == "MEGA_PACK_15"
        assert entry.metadata_["asset_breakdown"] == {
            "paid_energy": 15,
            "mode_codes": list(MEGA_PACK_MODE_CODES),
        }


@pytest.mark.asyncio
async def test_credit_is_idempotent_on_same_purchase() -> None:
    now_utc = datetime(2026, 2, 18, 12, 10, tzinfo=UTC)
    user_id = await _create_user("inv-a-credit-idempotent")

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="inv-a-credit-idempotent:init",
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

        first = await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_inv_a_credit_idempotent_1",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc,
        )
        second = await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_inv_a_credit_idempotent_1",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc,
        )

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True

    async with SessionLocal.begin() as session:
        count_stmt = select(func.count(LedgerEntry.id)).where(
            LedgerEntry.purchase_id == init.purchase_id,
            LedgerEntry.entry_type == "PURCHASE_CREDIT",
            LedgerEntry.direction == "CREDIT",
        )
        entry_count = await session.scalar(count_stmt)
        assert int(entry_count or 0) == 1

        purchase = await PurchasesRepo.get_by_id(session, init.purchase_id)
        assert purchase is not None
        assert purchase.status == "CREDITED"


@pytest.mark.asyncio
async def test_credit_contains_expected_breakdown_keys_for_friend_challenge_ticket() -> None:
    now_utc = datetime(2026, 2, 18, 12, 20, tzinfo=UTC)
    user_id = await _create_user("inv-a-credit-breakdown-keys")
    purchase_id, _ = await _create_credited_purchase(
        user_id=user_id,
        product_code="FRIEND_CHALLENGE_5",
        idempotency_prefix="inv-a-credit-breakdown-keys",
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        entry = await session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.purchase_id == purchase_id,
                LedgerEntry.entry_type == "PURCHASE_CREDIT",
                LedgerEntry.direction == "CREDIT",
            )
        )
        assert entry is not None
        breakdown = entry.metadata_["asset_breakdown"]
        assert isinstance(breakdown, dict)
        assert set(breakdown.keys()) == {"friend_challenge_tickets"}
        assert breakdown["friend_challenge_tickets"] == 1


@pytest.mark.asyncio
async def test_credit_mutates_wallet_only_by_expected_breakdown_delta() -> None:
    now_utc = datetime(2026, 2, 18, 12, 30, tzinfo=UTC)
    user_id = await _create_user("inv-a-credit-wallet-delta")

    async with SessionLocal.begin() as session:
        session.add(
            EnergyState(
                user_id=user_id,
                free_energy=7,
                paid_energy=2,
                free_cap=20,
                regen_interval_sec=1800,
                last_regen_at=now_utc,
                last_daily_topup_local_date=berlin_local_date(now_utc),
                version=0,
                updated_at=now_utc,
            )
        )

    await _create_credited_purchase(
        user_id=user_id,
        product_code="ENERGY_10",
        idempotency_prefix="inv-a-credit-wallet-delta",
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        state = await EnergyRepo.get_by_user_id(session, user_id)
        assert state is not None
        assert state.free_energy == 7
        assert state.paid_energy == 12
