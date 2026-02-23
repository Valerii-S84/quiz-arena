from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.models.promo_attempts import PromoAttempt
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=50_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="PromoDashboard",
            referred_by_user_id=None,
        )
        return user.id


async def _seed_dashboard_dataset(now_utc: datetime) -> None:
    user_1 = await _create_user("promo-dashboard-u1")
    user_2 = await _create_user("promo-dashboard-u2")
    user_3 = await _create_user("promo-dashboard-u3")

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                PromoCode(
                    id=1001,
                    code_hash="1" * 64,
                    code_prefix="CAMP1001",
                    campaign_name="dashboard-active-discount",
                    promo_type="PERCENT_DISCOUNT",
                    grant_premium_days=None,
                    discount_percent=50,
                    target_scope="PREMIUM_MONTH",
                    status="ACTIVE",
                    valid_from=now_utc - timedelta(days=1),
                    valid_until=now_utc + timedelta(days=1),
                    max_total_uses=500,
                    used_total=1,
                    max_uses_per_user=1,
                    new_users_only=False,
                    first_purchase_only=False,
                    created_by="integration-test",
                    created_at=now_utc - timedelta(days=1),
                    updated_at=now_utc - timedelta(hours=1),
                ),
                PromoCode(
                    id=1002,
                    code_hash="2" * 64,
                    code_prefix="CAMP1002",
                    campaign_name="dashboard-paused-recent",
                    promo_type="PERCENT_DISCOUNT",
                    grant_premium_days=None,
                    discount_percent=30,
                    target_scope="ENERGY_10",
                    status="PAUSED",
                    valid_from=now_utc - timedelta(days=1),
                    valid_until=now_utc + timedelta(days=1),
                    max_total_uses=500,
                    used_total=1,
                    max_uses_per_user=1,
                    new_users_only=False,
                    first_purchase_only=False,
                    created_by="integration-test",
                    created_at=now_utc - timedelta(days=1),
                    updated_at=now_utc - timedelta(minutes=20),
                ),
                PromoCode(
                    id=1003,
                    code_hash="3" * 64,
                    code_prefix="CAMP1003",
                    campaign_name="dashboard-paused-old",
                    promo_type="PREMIUM_GRANT",
                    grant_premium_days=7,
                    discount_percent=None,
                    target_scope="PREMIUM_ANY",
                    status="PAUSED",
                    valid_from=now_utc - timedelta(days=1),
                    valid_until=now_utc + timedelta(days=1),
                    max_total_uses=500,
                    used_total=0,
                    max_uses_per_user=1,
                    new_users_only=False,
                    first_purchase_only=False,
                    created_by="integration-test",
                    created_at=now_utc - timedelta(days=1),
                    updated_at=now_utc - timedelta(days=2),
                ),
                PromoCode(
                    id=1004,
                    code_hash="4" * 64,
                    code_prefix="CAMP1004",
                    campaign_name="dashboard-active-premium",
                    promo_type="PREMIUM_GRANT",
                    grant_premium_days=30,
                    discount_percent=None,
                    target_scope="PREMIUM_ANY",
                    status="ACTIVE",
                    valid_from=now_utc - timedelta(days=1),
                    valid_until=now_utc + timedelta(days=1),
                    max_total_uses=500,
                    used_total=1,
                    max_uses_per_user=1,
                    new_users_only=False,
                    first_purchase_only=False,
                    created_by="integration-test",
                    created_at=now_utc - timedelta(days=1),
                    updated_at=now_utc - timedelta(hours=2),
                ),
            ]
        )

        attempts: list[PromoAttempt] = [
            PromoAttempt(
                id=1,
                user_id=user_1,
                normalized_code_hash="a" * 64,
                result="ACCEPTED",
                source="API",
                attempted_at=now_utc - timedelta(minutes=30),
                metadata_={},
            ),
            PromoAttempt(
                id=2,
                user_id=user_2,
                normalized_code_hash="a" * 64,
                result="ACCEPTED",
                source="API",
                attempted_at=now_utc - timedelta(minutes=25),
                metadata_={},
            ),
            PromoAttempt(
                id=3,
                user_id=user_1,
                normalized_code_hash="b" * 64,
                result="INVALID",
                source="API",
                attempted_at=now_utc - timedelta(minutes=20),
                metadata_={},
            ),
            PromoAttempt(
                id=4,
                user_id=user_1,
                normalized_code_hash="c" * 64,
                result="EXPIRED",
                source="API",
                attempted_at=now_utc - timedelta(minutes=19),
                metadata_={},
            ),
            PromoAttempt(
                id=5,
                user_id=user_1,
                normalized_code_hash="d" * 64,
                result="NOT_APPLICABLE",
                source="API",
                attempted_at=now_utc - timedelta(minutes=18),
                metadata_={},
            ),
            PromoAttempt(
                id=6,
                user_id=user_1,
                normalized_code_hash="e" * 64,
                result="RATE_LIMITED",
                source="API",
                attempted_at=now_utc - timedelta(minutes=17),
                metadata_={},
            ),
        ]
        for idx in range(101):
            attempts.append(
                PromoAttempt(
                    id=100 + idx,
                    user_id=user_1 if idx % 2 == 0 else user_2,
                    normalized_code_hash="f" * 64,
                    result="INVALID",
                    source="API",
                    attempted_at=now_utc - timedelta(minutes=5),
                    metadata_={},
                )
            )
        session.add_all(attempts)

        session.add_all(
            [
                PromoRedemption(
                    id=uuid4(),
                    promo_code_id=1001,
                    user_id=user_1,
                    status="APPLIED",
                    reject_reason=None,
                    reserved_until=now_utc + timedelta(minutes=10),
                    applied_purchase_id=None,
                    grant_entitlement_id=None,
                    idempotency_key="dashboard-redemption-1",
                    validation_snapshot={"promo_type": "PERCENT_DISCOUNT"},
                    created_at=now_utc - timedelta(minutes=40),
                    applied_at=now_utc - timedelta(minutes=35),
                    updated_at=now_utc - timedelta(minutes=35),
                ),
                PromoRedemption(
                    id=uuid4(),
                    promo_code_id=1001,
                    user_id=user_2,
                    status="RESERVED",
                    reject_reason=None,
                    reserved_until=now_utc + timedelta(minutes=10),
                    applied_purchase_id=None,
                    grant_entitlement_id=None,
                    idempotency_key="dashboard-redemption-2",
                    validation_snapshot={"promo_type": "PERCENT_DISCOUNT"},
                    created_at=now_utc - timedelta(minutes=30),
                    applied_at=None,
                    updated_at=now_utc - timedelta(minutes=30),
                ),
                PromoRedemption(
                    id=uuid4(),
                    promo_code_id=1002,
                    user_id=user_3,
                    status="EXPIRED",
                    reject_reason=None,
                    reserved_until=now_utc - timedelta(minutes=5),
                    applied_purchase_id=None,
                    grant_entitlement_id=None,
                    idempotency_key="dashboard-redemption-3",
                    validation_snapshot={"promo_type": "PERCENT_DISCOUNT"},
                    created_at=now_utc - timedelta(minutes=50),
                    applied_at=None,
                    updated_at=now_utc - timedelta(minutes=10),
                ),
                PromoRedemption(
                    id=uuid4(),
                    promo_code_id=1004,
                    user_id=user_3,
                    status="APPLIED",
                    reject_reason=None,
                    reserved_until=None,
                    applied_purchase_id=None,
                    grant_entitlement_id=None,
                    idempotency_key="dashboard-redemption-4",
                    validation_snapshot={"promo_type": "PREMIUM_GRANT"},
                    created_at=now_utc - timedelta(minutes=45),
                    applied_at=now_utc - timedelta(minutes=45),
                    updated_at=now_utc - timedelta(minutes=45),
                ),
            ]
        )
