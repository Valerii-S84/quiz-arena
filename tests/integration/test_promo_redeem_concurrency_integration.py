from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.promo.errors import PromoAlreadyUsedError
from app.economy.promo.service import PromoService
from app.services.promo_codes import hash_promo_code, normalize_promo_code

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=70_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="PromoConcurrency",
            referred_by_user_id=None,
        )
        return user.id


async def _create_discount_code(*, raw_code: str, now_utc: datetime) -> PromoCode:
    normalized = normalize_promo_code(raw_code)
    code_hash = hash_promo_code(
        normalized_code=normalized,
        pepper=get_settings().promo_secret_pepper,
    )

    promo_id = abs(hash((raw_code, "concurrency"))) % 1_000_000_000 + 1
    promo_code = PromoCode(
        id=promo_id,
        code_hash=code_hash,
        code_prefix=normalized[:8] or "PROMO",
        campaign_name="integration-promo-concurrency",
        promo_type="PERCENT_DISCOUNT",
        grant_premium_days=None,
        discount_percent=40,
        target_scope="ENERGY_10",
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

    async with SessionLocal.begin() as session:
        session.add(promo_code)
        await session.flush()

    return promo_code


@pytest.mark.asyncio
async def test_parallel_redeem_collision_allows_only_one_redemption() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("promo-parallel-redeem")
    promo_code = await _create_discount_code(raw_code="PARALLEL-40", now_utc=now_utc)
    barrier = asyncio.Event()

    async def _attempt(idempotency_key: str) -> str:
        await barrier.wait()
        try:
            async with SessionLocal.begin() as session:
                await PromoService.redeem(
                    session,
                    user_id=user_id,
                    promo_code="PARALLEL-40",
                    idempotency_key=idempotency_key,
                    now_utc=now_utc,
                )
            return "accepted"
        except PromoAlreadyUsedError:
            return "already_used"

    task_1 = asyncio.create_task(_attempt("promo-parallel-1"))
    task_2 = asyncio.create_task(_attempt("promo-parallel-2"))
    barrier.set()
    outcomes = await asyncio.gather(task_1, task_2)

    assert sorted(outcomes) == ["accepted", "already_used"]

    async with SessionLocal.begin() as session:
        stmt = select(func.count(PromoRedemption.id)).where(
            PromoRedemption.promo_code_id == promo_code.id,
            PromoRedemption.user_id == user_id,
        )
        assert (await session.scalar(stmt)) == 1
