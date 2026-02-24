from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.core.config import get_settings
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.session import SessionLocal
from app.economy.promo.constants import PROMO_DISCOUNT_RESERVATION_TTL
from app.economy.promo.service import PromoService
from app.economy.purchases.errors import PurchasePrecheckoutValidationError
from app.economy.purchases.service import PurchaseService
from app.services.promo_codes import hash_promo_code, normalize_promo_code
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


async def _create_discount_code(
    *,
    raw_code: str,
    now_utc: datetime,
    target_scope: str = "ENERGY_10",
) -> int:
    normalized = normalize_promo_code(raw_code)
    code_hash = hash_promo_code(
        normalized_code=normalized,
        pepper=get_settings().promo_secret_pepper,
    )
    promo_code_id = abs(hash((raw_code, target_scope))) % 1_000_000_000 + 1

    async with SessionLocal.begin() as session:
        session.add(
            PromoCode(
                id=promo_code_id,
                code_hash=code_hash,
                code_prefix=normalized[:8] or "PROMO",
                campaign_name="inv-d-promo-ttl",
                promo_type="PERCENT_DISCOUNT",
                grant_premium_days=None,
                discount_percent=35,
                target_scope=target_scope,
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
    return promo_code_id


@pytest.mark.asyncio
async def test_promo_reservation_ttl_is_15_minutes() -> None:
    now_utc = datetime(2026, 2, 18, 16, 0, tzinfo=UTC)
    user_id = await _create_user("inv-d-promo-ttl")
    await _create_discount_code(raw_code="INV-D-TTL-15", now_utc=now_utc)

    async with SessionLocal.begin() as session:
        redeem_result = await PromoService.redeem(
            session,
            user_id=user_id,
            promo_code="INV D TTL 15",
            idempotency_key="inv-d-promo-ttl:redeem",
            now_utc=now_utc,
        )

    assert redeem_result.result_type == "PERCENT_DISCOUNT"
    assert redeem_result.reserved_until is not None
    assert redeem_result.reserved_until - now_utc == PROMO_DISCOUNT_RESERVATION_TTL

    async with SessionLocal.begin() as session:
        redemption = await session.get(PromoRedemption, redeem_result.redemption_id)
        assert redemption is not None
        assert redemption.status == "RESERVED"
        assert redemption.reserved_until is not None
        assert redemption.reserved_until - redemption.updated_at == PROMO_DISCOUNT_RESERVATION_TTL


@pytest.mark.asyncio
async def test_promo_reservation_expiry_blocks_precheckout_validation() -> None:
    now_utc = datetime(2026, 2, 18, 16, 10, tzinfo=UTC)
    user_id = await _create_user("inv-d-promo-expiry")
    await _create_discount_code(raw_code="INV-D-EXP-35", now_utc=now_utc, target_scope="ENERGY_10")

    async with SessionLocal.begin() as session:
        redeem_result = await PromoService.redeem(
            session,
            user_id=user_id,
            promo_code="INV D EXP 35",
            idempotency_key="inv-d-promo-expiry:redeem",
            now_utc=now_utc,
        )
        assert redeem_result.result_type == "PERCENT_DISCOUNT"
        redemption_id = redeem_result.redemption_id

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="inv-d-promo-expiry:init",
            now_utc=now_utc,
            promo_redemption_id=redemption_id,
        )

    with pytest.raises(PurchasePrecheckoutValidationError):
        async with SessionLocal.begin() as session:
            await PurchaseService.validate_precheckout(
                session,
                user_id=user_id,
                invoice_payload=init.invoice_payload,
                total_amount=init.final_stars_amount,
                now_utc=now_utc + timedelta(minutes=16),
            )

    async with SessionLocal.begin() as session:
        purchase = await PurchasesRepo.get_by_id(session, init.purchase_id)
        assert purchase is not None
        assert purchase.status == "CREATED"

        redemption = await session.get(PromoRedemption, redemption_id)
        assert redemption is not None
        assert redemption.status == "RESERVED"
