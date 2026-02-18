from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.purchases.errors import PremiumDowngradeNotAllowedError
from app.economy.purchases.service import PurchaseService

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=30_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="Premium",
            referred_by_user_id=None,
        )
        return user.id


@pytest.mark.asyncio
async def test_premium_month_purchase_grants_active_entitlement() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("premium-month")

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="PREMIUM_MONTH",
            idempotency_key="premium-month-1",
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
        result = await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_premium_month_1",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc,
        )

    assert result.idempotent_replay is False
    assert result.product_code == "PREMIUM_MONTH"

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, init.purchase_id)
        assert purchase is not None
        assert purchase.status == "CREDITED"

        ent_stmt = select(Entitlement).where(
            Entitlement.user_id == user_id,
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.status == "ACTIVE",
        )
        entitlement = await session.scalar(ent_stmt)
        assert entitlement is not None
        assert entitlement.scope == "PREMIUM_MONTH"
        assert entitlement.starts_at == now_utc
        assert entitlement.ends_at == now_utc + timedelta(days=30)

        ledger_stmt = select(LedgerEntry).where(
            LedgerEntry.idempotency_key == f"credit:premium:{init.purchase_id}",
        )
        ledger_entry = await session.scalar(ledger_stmt)
        assert ledger_entry is not None
        assert ledger_entry.asset == "PREMIUM"
        assert ledger_entry.amount == 30


@pytest.mark.asyncio
async def test_premium_upgrade_extends_from_existing_end_and_revokes_old_entitlement() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("premium-upgrade")
    existing_end = now_utc + timedelta(days=10)

    async with SessionLocal.begin() as session:
        session.add(
            Entitlement(
                user_id=user_id,
                entitlement_type="PREMIUM",
                scope="PREMIUM_SEASON",
                status="ACTIVE",
                starts_at=now_utc - timedelta(days=20),
                ends_at=existing_end,
                source_purchase_id=None,
                idempotency_key=f"entitlement-existing-{uuid4().hex}",
                metadata_={},
                created_at=now_utc - timedelta(days=20),
                updated_at=now_utc,
            )
        )
        await session.flush()

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="PREMIUM_YEAR",
            idempotency_key="premium-upgrade-year-1",
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
        await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_premium_upgrade_1",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc,
        )

    async with SessionLocal.begin() as session:
        active_stmt = select(Entitlement).where(
            Entitlement.user_id == user_id,
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.status == "ACTIVE",
        )
        active_entitlement = await session.scalar(active_stmt)
        assert active_entitlement is not None
        assert active_entitlement.scope == "PREMIUM_YEAR"
        assert active_entitlement.starts_at == now_utc
        assert active_entitlement.ends_at == existing_end + timedelta(days=365)

        revoked_stmt = select(Entitlement).where(
            Entitlement.user_id == user_id,
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.status == "REVOKED",
            Entitlement.scope == "PREMIUM_SEASON",
        )
        revoked_entitlement = await session.scalar(revoked_stmt)
        assert revoked_entitlement is not None


@pytest.mark.asyncio
async def test_premium_downgrade_is_blocked_during_active_higher_tier() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("premium-downgrade")

    async with SessionLocal.begin() as session:
        session.add(
            Entitlement(
                user_id=user_id,
                entitlement_type="PREMIUM",
                scope="PREMIUM_YEAR",
                status="ACTIVE",
                starts_at=now_utc - timedelta(days=15),
                ends_at=now_utc + timedelta(days=120),
                source_purchase_id=None,
                idempotency_key=f"entitlement-active-year-{uuid4().hex}",
                metadata_={},
                created_at=now_utc - timedelta(days=15),
                updated_at=now_utc,
            )
        )
        await session.flush()

    with pytest.raises(PremiumDowngradeNotAllowedError):
        async with SessionLocal.begin() as session:
            await PurchaseService.init_purchase(
                session,
                user_id=user_id,
                product_code="PREMIUM_STARTER",
                idempotency_key="premium-downgrade-1",
                now_utc=now_utc,
            )

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_idempotency_key(session, "premium-downgrade-1")
        assert purchase is None
