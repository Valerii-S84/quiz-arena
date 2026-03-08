from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.db.models.promo_codes import PromoCode
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.main import app
from app.services.admin.auth import build_access_token
from app.services.promo_codes import hash_promo_code, normalize_promo_code
from app.services.promo_encryption import encrypt_promo_code

UTC = timezone.utc


def admin_headers(*, role: str) -> dict[str, str]:
    token = build_access_token(
        settings=get_settings(),
        email="admin@example.com",
        role=role,
        two_factor_verified=True,
    )
    return {"Authorization": f"Bearer {token}"}


async def create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=90_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"A{uuid4().hex[:10]}",
            username=None,
            first_name="AdminPromo",
            referred_by_user_id=None,
        )
        return user.id


async def redeem_code(*, user_id: int, promo_code: str, suffix: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/internal/promo/redeem",
            json={
                "user_id": user_id,
                "promo_code": promo_code,
                "idempotency_key": f"admin-runtime-redeem-{suffix}",
            },
            headers={"X-Internal-Token": get_settings().internal_api_token},
        )
    assert response.status_code == 200


async def create_discount_promo_via_api(*, code: str = "WELCOME50") -> dict[str, object]:
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/admin/promo",
            json={
                "code": code,
                "campaign_name": "Fruehling",
                "discount_type": "PERCENT",
                "discount_value": 50,
                "applicable_products": ["PREMIUM_MONTH"],
                "max_total_uses": 10,
                "max_per_user": 1,
            },
            headers=admin_headers(role="admin"),
        )
    assert response.status_code == 200
    return response.json()


async def insert_promo(*, promo_id: int, raw_code: str, now_utc: datetime) -> None:
    normalized = normalize_promo_code(raw_code)
    code_hash = hash_promo_code(
        normalized_code=normalized,
        pepper=get_settings().promo_secret_pepper,
    )
    async with SessionLocal.begin() as session:
        session.add(
            PromoCode(
                id=promo_id,
                code_hash=code_hash,
                code_prefix=normalized[:8],
                code_encrypted=encrypt_promo_code(raw_code),
                campaign_name="manual-seed",
                promo_type="PERCENT_DISCOUNT",
                grant_premium_days=None,
                discount_percent=25,
                discount_type="PERCENT",
                discount_value=25,
                applicable_products=["ENERGY_10"],
                target_scope="ENERGY_10",
                status="ACTIVE",
                valid_from=now_utc - timedelta(days=1),
                valid_until=now_utc + timedelta(days=1),
                max_total_uses=20,
                used_total=0,
                max_uses_per_user=1,
                new_users_only=False,
                first_purchase_only=False,
                created_by="integration-test",
                created_at=now_utc,
                updated_at=now_utc,
            )
        )
