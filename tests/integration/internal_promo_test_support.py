from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.db.models.promo_codes import PromoCode
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.main import app
from app.services.promo_codes import hash_promo_code, normalize_promo_code

UTC = timezone.utc


async def create_user(seed: str) -> int:
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


async def create_promo_code(
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


async def post_redeem(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
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
