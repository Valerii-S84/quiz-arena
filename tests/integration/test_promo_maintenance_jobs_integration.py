from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.workers.tasks.promo_maintenance import (
    run_promo_campaign_status_rollover_async,
    run_promo_reservation_expiry_async,
)

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=50_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="PromoJob",
            referred_by_user_id=None,
        )
        return user.id


async def _create_discount_code(*, code_id: int, now_utc: datetime, status: str = "ACTIVE") -> PromoCode:
    promo_code = PromoCode(
        id=code_id,
        code_hash=uuid4().hex + uuid4().hex,
        code_prefix="PROMO",
        campaign_name="promo-maintenance",
        promo_type="PERCENT_DISCOUNT",
        grant_premium_days=None,
        discount_percent=30,
        target_scope="ENERGY_10",
        status=status,
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
async def test_promo_reservation_expiry_marks_only_overdue_reserved_redemptions() -> None:
    now_utc = datetime.now(UTC)
    user_id_expired = await _create_user("promo-job-expiry-1")
    user_id_active = await _create_user("promo-job-expiry-2")
    user_id_applied = await _create_user("promo-job-expiry-3")
    promo_code = await _create_discount_code(code_id=101, now_utc=now_utc)

    expired_redemption_id = uuid4()
    active_redemption_id = uuid4()
    applied_redemption_id = uuid4()

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                PromoRedemption(
                    id=expired_redemption_id,
                    promo_code_id=promo_code.id,
                    user_id=user_id_expired,
                    status="RESERVED",
                    reject_reason=None,
                    reserved_until=now_utc - timedelta(minutes=2),
                    applied_purchase_id=None,
                    grant_entitlement_id=None,
                    idempotency_key=f"reservation-expired-{uuid4().hex}",
                    validation_snapshot={},
                    created_at=now_utc,
                    applied_at=None,
                    updated_at=now_utc,
                ),
                PromoRedemption(
                    id=active_redemption_id,
                    promo_code_id=promo_code.id,
                    user_id=user_id_active,
                    status="RESERVED",
                    reject_reason=None,
                    reserved_until=now_utc + timedelta(minutes=5),
                    applied_purchase_id=None,
                    grant_entitlement_id=None,
                    idempotency_key=f"reservation-active-{uuid4().hex}",
                    validation_snapshot={},
                    created_at=now_utc,
                    applied_at=None,
                    updated_at=now_utc,
                ),
                PromoRedemption(
                    id=applied_redemption_id,
                    promo_code_id=promo_code.id,
                    user_id=user_id_applied,
                    status="APPLIED",
                    reject_reason=None,
                    reserved_until=now_utc - timedelta(minutes=5),
                    applied_purchase_id=None,
                    grant_entitlement_id=None,
                    idempotency_key=f"reservation-applied-{uuid4().hex}",
                    validation_snapshot={},
                    created_at=now_utc,
                    applied_at=now_utc,
                    updated_at=now_utc,
                ),
            ]
        )
        await session.flush()

    result = await run_promo_reservation_expiry_async()
    assert result["expired_redemptions"] == 1

    async with SessionLocal.begin() as session:
        expired = await session.get(PromoRedemption, expired_redemption_id)
        active = await session.get(PromoRedemption, active_redemption_id)
        applied = await session.get(PromoRedemption, applied_redemption_id)
        assert expired is not None and expired.status == "EXPIRED"
        assert active is not None and active.status == "RESERVED"
        assert applied is not None and applied.status == "APPLIED"


@pytest.mark.asyncio
async def test_promo_campaign_status_rollover_expires_and_depletes_active_codes() -> None:
    now_utc = datetime.now(UTC)

    expired_code_id = 201
    depleted_code_id = 202
    active_code_id = 203

    await _create_discount_code(code_id=expired_code_id, now_utc=now_utc)
    await _create_discount_code(code_id=depleted_code_id, now_utc=now_utc)
    await _create_discount_code(code_id=active_code_id, now_utc=now_utc)

    async with SessionLocal.begin() as session:
        expired_code = await session.get(PromoCode, expired_code_id)
        depleted_code = await session.get(PromoCode, depleted_code_id)
        active_code = await session.get(PromoCode, active_code_id)
        assert expired_code is not None
        assert depleted_code is not None
        assert active_code is not None

        expired_code.valid_until = now_utc - timedelta(minutes=1)
        depleted_code.max_total_uses = 5
        depleted_code.used_total = 5
        active_code.max_total_uses = 10
        active_code.used_total = 3
        await session.flush()

    result = await run_promo_campaign_status_rollover_async()
    assert result["expired_campaigns"] == 1
    assert result["depleted_campaigns"] == 1
    assert result["updated_campaigns"] == 2

    async with SessionLocal.begin() as session:
        stmt = select(PromoCode.id, PromoCode.status).where(PromoCode.id.in_([expired_code_id, depleted_code_id, active_code_id]))
        rows = dict((row_id, status) for row_id, status in (await session.execute(stmt)).all())
        assert rows[expired_code_id] == "EXPIRED"
        assert rows[depleted_code_id] == "DEPLETED"
        assert rows[active_code_id] == "ACTIVE"
