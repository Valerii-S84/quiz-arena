from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.promo_repo import PromoRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.promo.constants import PROMO_DISCOUNT_RESERVATION_TTL
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


async def _create_validated_redemption(
    *,
    promo_code_id: int,
    user_id: int,
    now_utc: datetime,
) -> UUID:
    redemption_id = uuid4()
    async with SessionLocal.begin() as session:
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
    return redemption_id


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
        assert redemption.reserved_until - redemption.updated_at == PROMO_DISCOUNT_RESERVATION_TTL


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


@pytest.mark.asyncio
async def test_init_purchase_replaces_active_invoice_with_new_discounted_one() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("promo-reinvoice")
    first_promo_code_id, first_redemption_id = await _create_discount_promo_redemption(
        user_id=user_id,
        product_code="ENERGY_10",
        discount_percent=20,
        now_utc=now_utc,
    )
    _, second_redemption_id = await _create_discount_promo_redemption(
        user_id=user_id,
        product_code="ENERGY_10",
        discount_percent=50,
        now_utc=now_utc + timedelta(minutes=1),
    )

    async with SessionLocal.begin() as session:
        first = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="promo-reinvoice-1",
            now_utc=now_utc,
            promo_redemption_id=first_redemption_id,
        )
        second = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="promo-reinvoice-2",
            now_utc=now_utc + timedelta(minutes=1),
            promo_redemption_id=second_redemption_id,
        )

    assert first.purchase_id != second.purchase_id
    assert first.final_stars_amount == 4
    assert second.final_stars_amount == 3

    async with SessionLocal.begin() as session:
        first_purchase = await PurchasesRepo.get_by_id(session, first.purchase_id)
        assert first_purchase is not None
        assert first_purchase.status == "FAILED"
        assert first_purchase.applied_promo_code_id == first_promo_code_id

        first_redemption = await PromoRepo.get_redemption_by_id(session, first_redemption_id)
        assert first_redemption is not None
        assert first_redemption.status == "EXPIRED"

        second_redemption = await PromoRepo.get_redemption_by_id(session, second_redemption_id)
        assert second_redemption is not None
        assert second_redemption.status == "RESERVED"
        assert second_redemption.applied_purchase_id == second.purchase_id


@pytest.mark.asyncio
async def test_init_purchase_enforces_max_total_uses_before_invoice_creation() -> None:
    now_utc = datetime.now(UTC)
    promo_code_id, _ = await _create_discount_promo_redemption(
        user_id=await _create_user("promo-max-uses-seed"),
        product_code="ENERGY_10",
        discount_percent=50,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        promo_code = await PromoRepo.get_code_by_id(session, promo_code_id)
        assert promo_code is not None
        promo_code.max_total_uses = 1

    user_ids = [await _create_user(f"promo-max-uses-{idx}") for idx in range(10)]
    redemption_ids = [
        await _create_validated_redemption(
            promo_code_id=promo_code_id,
            user_id=user_id,
            now_utc=now_utc,
        )
        for user_id in user_ids
    ]
    barrier = asyncio.Event()

    async def _attempt(idx: int) -> str:
        await barrier.wait()
        try:
            async with SessionLocal.begin() as session:
                await PurchaseService.init_purchase(
                    session,
                    user_id=user_ids[idx],
                    product_code="ENERGY_10",
                    idempotency_key=f"promo-max-uses:{idx}",
                    now_utc=now_utc,
                    promo_redemption_id=redemption_ids[idx],
                )
            return "accepted"
        except PurchaseInitValidationError:
            return "rejected"

    tasks = [asyncio.create_task(_attempt(idx)) for idx in range(len(user_ids))]
    barrier.set()
    outcomes = await asyncio.gather(*tasks)

    assert outcomes.count("accepted") == 1
    assert outcomes.count("rejected") == 9
