from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.promo_repo import PromoRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.purchases.errors import (
    PurchaseInitValidationError,
    PurchasePrecheckoutValidationError,
)
from app.economy.purchases.service import PurchaseService

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=20_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="Promo",
            referred_by_user_id=None,
        )
        return user.id


async def _create_discount_promo_redemption(
    *,
    user_id: int,
    product_code: str,
    discount_percent: int,
    now_utc: datetime,
) -> tuple[int, UUID]:
    promo_code_id = abs(hash((user_id, product_code, discount_percent))) % 1_000_000_000 + 1
    redemption_id = uuid4()

    async with SessionLocal.begin() as session:
        session.add(
            PromoCode(
                id=promo_code_id,
                code_hash=uuid4().hex + uuid4().hex,
                code_prefix="PROMO",
                campaign_name="integration-discount",
                promo_type="PERCENT_DISCOUNT",
                grant_premium_days=None,
                discount_percent=discount_percent,
                target_scope=product_code,
                status="ACTIVE",
                valid_from=now_utc - timedelta(days=1),
                valid_until=now_utc + timedelta(days=1),
                max_total_uses=100,
                used_total=0,
                max_uses_per_user=1,
                new_users_only=False,
                first_purchase_only=False,
                created_by="integration-test",
                created_at=now_utc,
                updated_at=now_utc,
            )
        )
        session.add(
            PromoRedemption(
                id=redemption_id,
                promo_code_id=promo_code_id,
                user_id=user_id,
                status="VALIDATED",
                reject_reason=None,
                reserved_until=None,
                applied_purchase_id=None,
                grant_entitlement_id=None,
                idempotency_key=f"promo-redemption:{uuid4().hex}",
                validation_snapshot={},
                created_at=now_utc,
                applied_at=None,
                updated_at=now_utc,
            )
        )
        await session.flush()

    return promo_code_id, redemption_id


@pytest.mark.asyncio
async def test_init_purchase_applies_discount_and_reserves_redemption() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("promo-init")
    promo_code_id, redemption_id = await _create_discount_promo_redemption(
        user_id=user_id,
        product_code="ENERGY_10",
        discount_percent=50,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        result = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="promo-init-1",
            now_utc=now_utc,
            promo_redemption_id=redemption_id,
        )

    assert result.base_stars_amount == 5
    assert result.discount_stars_amount == 2
    assert result.final_stars_amount == 3
    assert result.applied_promo_code_id == promo_code_id
    assert result.idempotent_replay is False

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, result.purchase_id)
        assert purchase is not None
        assert purchase.base_stars_amount == 5
        assert purchase.discount_stars_amount == 2
        assert purchase.stars_amount == 3
        assert purchase.applied_promo_code_id == promo_code_id

        redemption = await PromoRepo.get_redemption_by_id(session, redemption_id)
        assert redemption is not None
        assert redemption.status == "RESERVED"
        assert redemption.applied_purchase_id == result.purchase_id
        assert redemption.reserved_until is not None
        assert redemption.reserved_until > now_utc


@pytest.mark.asyncio
async def test_validate_precheckout_rejects_expired_promo_reservation() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("promo-precheckout-expired")
    _, redemption_id = await _create_discount_promo_redemption(
        user_id=user_id,
        product_code="ENERGY_10",
        discount_percent=50,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        result = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="promo-precheckout-expired-1",
            now_utc=now_utc,
            promo_redemption_id=redemption_id,
        )

    async with SessionLocal.begin() as session:
        redemption = await PromoRepo.get_redemption_by_id(session, redemption_id)
        assert redemption is not None
        redemption.reserved_until = now_utc - timedelta(minutes=1)
        redemption.updated_at = now_utc

    with pytest.raises(PurchasePrecheckoutValidationError):
        async with SessionLocal.begin() as session:
            await PurchaseService.validate_precheckout(
                session,
                user_id=user_id,
                invoice_payload=result.invoice_payload,
                total_amount=result.final_stars_amount,
                now_utc=now_utc,
            )

    async with SessionLocal.begin() as session:
        redemption = await PromoRepo.get_redemption_by_id(session, redemption_id)
        assert redemption is not None
        assert redemption.status == "RESERVED"


@pytest.mark.asyncio
async def test_successful_payment_applies_redemption_once_and_increments_used_total() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("promo-success")
    promo_code_id, redemption_id = await _create_discount_promo_redemption(
        user_id=user_id,
        product_code="ENERGY_10",
        discount_percent=50,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="promo-success-1",
            now_utc=now_utc,
            promo_redemption_id=redemption_id,
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
            telegram_payment_charge_id="tg_charge_promo_success_1",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc,
        )
        second = await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id="tg_charge_promo_success_1",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc,
        )

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, init.purchase_id)
        assert purchase is not None
        assert purchase.status == "CREDITED"

        redemption = await PromoRepo.get_redemption_by_id(session, redemption_id)
        assert redemption is not None
        assert redemption.status == "APPLIED"
        assert redemption.applied_at is not None

        promo_code = await PromoRepo.get_code_by_id(session, promo_code_id)
        assert promo_code is not None
        assert promo_code.used_total == 1


@pytest.mark.asyncio
async def test_init_purchase_rejects_not_applicable_scope() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("promo-scope-mismatch")
    _, redemption_id = await _create_discount_promo_redemption(
        user_id=user_id,
        product_code="MEGA_PACK_15",
        discount_percent=50,
        now_utc=now_utc,
    )

    with pytest.raises(PurchaseInitValidationError):
        async with SessionLocal.begin() as session:
            await PurchaseService.init_purchase(
                session,
                user_id=user_id,
                product_code="ENERGY_10",
                idempotency_key="promo-scope-mismatch-1",
                now_utc=now_utc,
                promo_redemption_id=redemption_id,
            )

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_idempotency_key(session, "promo-scope-mismatch-1")
        assert purchase is None
