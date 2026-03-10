from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from tests.integration.stable_ids import stable_int_id, stable_telegram_user_id

UTC = timezone.utc


async def create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=stable_telegram_user_id(prefix=20_000_000_000, seed=seed),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="Promo",
            referred_by_user_id=None,
        )
        return user.id


async def create_discount_promo_redemption(
    *,
    user_id: int,
    product_code: str,
    discount_percent: int,
    now_utc: datetime,
) -> tuple[int, UUID]:
    promo_code_id = stable_int_id(user_id, product_code, discount_percent)
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


async def create_validated_redemption(
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
