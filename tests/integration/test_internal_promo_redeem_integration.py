from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models.promo_attempts import PromoAttempt
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.repo.purchases_repo import PurchasesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.promo.constants import PROMO_DISCOUNT_RESERVATION_TTL
from app.economy.purchases.service import PurchaseService
from app.main import app
from app.services.promo_codes import hash_promo_code, normalize_promo_code

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=40_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="PromoAPI",
            referred_by_user_id=None,
        )
        return user.id


async def _create_promo_code(
    *,
    raw_code: str,
    promo_type: str,
    now_utc: datetime,
    grant_premium_days: int | None = None,
    discount_percent: int | None = None,
    target_scope: str = "PREMIUM_ANY",
    first_purchase_only: bool = False,
    new_users_only: bool = False,
) -> PromoCode:
    normalized = normalize_promo_code(raw_code)
    code_hash = hash_promo_code(
        normalized_code=normalized,
        pepper=get_settings().promo_secret_pepper,
    )

    promo_id = abs(hash((raw_code, promo_type, target_scope))) % 1_000_000_000 + 1
    promo_code = PromoCode(
        id=promo_id,
        code_hash=code_hash,
        code_prefix=normalized[:8] or "PROMO",
        campaign_name="integration-promo-redeem",
        promo_type=promo_type,
        grant_premium_days=grant_premium_days,
        discount_percent=discount_percent,
        target_scope=target_scope,
        status="ACTIVE",
        valid_from=now_utc - timedelta(days=1),
        valid_until=now_utc + timedelta(days=1),
        max_total_uses=100,
        used_total=0,
        max_uses_per_user=1,
        new_users_only=new_users_only,
        first_purchase_only=first_purchase_only,
        created_by="integration-test",
        created_at=now_utc,
        updated_at=now_utc,
    )

    async with SessionLocal.begin() as session:
        session.add(promo_code)
        await session.flush()

    return promo_code


async def _post_redeem(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/internal/promo/redeem",
            json=payload,
            headers={"X-Internal-Token": get_settings().internal_api_token},
        )
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_redeem_premium_grant_applies_entitlement_and_marks_redemption_applied() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("promo-grant")
    await _create_promo_code(
        raw_code="WILLKOMMEN-7",
        promo_type="PREMIUM_GRANT",
        grant_premium_days=7,
        discount_percent=None,
        target_scope="PREMIUM_ANY",
        now_utc=now_utc,
    )

    status_code, payload = await _post_redeem(
        {
            "user_id": user_id,
            "promo_code": "willkommen 7",
            "idempotency_key": "promo-grant-1",
        }
    )

    assert status_code == 200
    assert payload["result_type"] == "PREMIUM_GRANT"
    assert payload["premium_days"] == 7
    assert payload["premium_ends_at"] is not None

    redemption_id = UUID(payload["redemption_id"])
    async with SessionLocal.begin() as session:
        redemption = await session.get(PromoRedemption, redemption_id)
        assert redemption is not None
        assert redemption.status == "APPLIED"
        assert redemption.grant_entitlement_id is not None


@pytest.mark.asyncio
async def test_redeem_discount_returns_reservation_and_is_idempotent_for_same_key() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("promo-discount")
    promo_code = await _create_promo_code(
        raw_code="WILLKOMMEN-50",
        promo_type="PERCENT_DISCOUNT",
        grant_premium_days=None,
        discount_percent=50,
        target_scope="PREMIUM_MONTH",
        now_utc=now_utc,
    )

    first_status, first_payload = await _post_redeem(
        {
            "user_id": user_id,
            "promo_code": "WILLKOMMEN-50",
            "idempotency_key": "promo-discount-1",
        }
    )
    second_status, second_payload = await _post_redeem(
        {
            "user_id": user_id,
            "promo_code": "WILLKOMMEN-50",
            "idempotency_key": "promo-discount-1",
        }
    )

    assert first_status == 200
    assert second_status == 200
    assert first_payload["result_type"] == "PERCENT_DISCOUNT"
    assert first_payload["discount_percent"] == 50
    assert first_payload["target_scope"] == "PREMIUM_MONTH"
    assert second_payload["redemption_id"] == first_payload["redemption_id"]
    assert second_payload["reserved_until"] == first_payload["reserved_until"]

    async with SessionLocal.begin() as session:
        stmt = select(func.count(PromoRedemption.id)).where(
            PromoRedemption.promo_code_id == promo_code.id,
            PromoRedemption.user_id == user_id,
        )
        assert (await session.scalar(stmt)) == 1
        redemption = await session.get(PromoRedemption, UUID(first_payload["redemption_id"]))
        assert redemption is not None
        assert redemption.reserved_until is not None
        assert redemption.reserved_until - redemption.updated_at == PROMO_DISCOUNT_RESERVATION_TTL


@pytest.mark.asyncio
async def test_redeem_returns_conflict_when_same_code_used_with_new_idempotency_key() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("promo-already-used")
    await _create_promo_code(
        raw_code="EINMAL-50",
        promo_type="PERCENT_DISCOUNT",
        grant_premium_days=None,
        discount_percent=50,
        target_scope="ENERGY_10",
        now_utc=now_utc,
    )

    first_status, _ = await _post_redeem(
        {
            "user_id": user_id,
            "promo_code": "EINMAL-50",
            "idempotency_key": "promo-used-1",
        }
    )
    second_status, second_payload = await _post_redeem(
        {
            "user_id": user_id,
            "promo_code": "EINMAL-50",
            "idempotency_key": "promo-used-2",
        }
    )

    assert first_status == 200
    assert second_status == 409
    assert second_payload["detail"]["code"] == "E_PROMO_ALREADY_USED"


@pytest.mark.asyncio
async def test_redeem_enforces_rate_limit_after_five_failed_attempts() -> None:
    user_id = await _create_user("promo-rate-limit")
    for idx in range(5):
        status_code, payload = await _post_redeem(
            {
                "user_id": user_id,
                "promo_code": f"INVALID-{idx}",
                "idempotency_key": f"promo-invalid-{idx}",
            }
        )
        assert status_code == 404
        assert payload["detail"]["code"] == "E_PROMO_INVALID"

    blocked_status, blocked_payload = await _post_redeem(
        {
            "user_id": user_id,
            "promo_code": "INVALID-BLOCKED",
            "idempotency_key": "promo-invalid-blocked",
        }
    )

    assert blocked_status == 429
    assert blocked_payload["detail"]["code"] == "E_PROMO_RATE_LIMITED"

    async with SessionLocal.begin() as session:
        stmt = select(func.count(PromoAttempt.id)).where(
            PromoAttempt.user_id == user_id,
            PromoAttempt.result == "RATE_LIMITED",
        )
        assert (await session.scalar(stmt)) == 1


@pytest.mark.asyncio
async def test_redeem_first_purchase_only_rejects_user_with_existing_purchase() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("promo-first-purchase")
    await _create_promo_code(
        raw_code="FIRSTONLY-30",
        promo_type="PERCENT_DISCOUNT",
        grant_premium_days=None,
        discount_percent=30,
        target_scope="ENERGY_10",
        first_purchase_only=True,
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="existing-purchase-for-promo",
            now_utc=now_utc,
        )
        purchase = await PurchasesRepo.get_by_id(session, init.purchase_id)
        assert purchase is not None

    status_code, payload = await _post_redeem(
        {
            "user_id": user_id,
            "promo_code": "FIRSTONLY30",
            "idempotency_key": "promo-first-only-1",
        }
    )
    assert status_code == 422
    assert payload["detail"]["code"] == "E_PROMO_NOT_APPLICABLE"
