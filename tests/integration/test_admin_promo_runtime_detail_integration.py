from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.admin_audit_log import AdminAuditLog
from app.db.models.promo_audit_log import PromoAuditLog
from app.db.models.promo_codes import PromoCode
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.main import app
from app.services.admin.auth import build_access_token
from app.services.promo_encryption import decrypt_promo_code


def _admin_headers(*, role: str) -> dict[str, str]:
    token = build_access_token(
        settings=get_settings(),
        email="admin@example.com",
        role=role,
        two_factor_verified=True,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_promo_detail_reveals_code_only_for_super_admin() -> None:
    async with SessionLocal.begin() as session:
        await UsersRepo.create(
            session,
            telegram_user_id=91_000_000_001,
            referral_code=f"B{uuid4().hex[:10]}",
            username=None,
            first_name="Detail",
            referred_by_user_id=None,
        )

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        create_response = await client.post(
            "/admin/promo",
            json={
                "code": "SECRET30",
                "campaign_name": "Detail",
                "discount_type": "PERCENT",
                "discount_value": 30,
                "applicable_products": ["ENERGY_10"],
                "max_total_uses": 3,
                "max_per_user": 1,
            },
            headers=_admin_headers(role="admin"),
        )
        promo_id = int(create_response.json()["id"])
        admin_detail = await client.get(
            f"/admin/promo/{promo_id}",
            headers=_admin_headers(role="admin"),
        )
        super_admin_detail = await client.get(
            f"/admin/promo/{promo_id}",
            params={"reveal": "true"},
            headers=_admin_headers(role="super_admin"),
        )

    assert admin_detail.status_code == 200
    assert admin_detail.json()["raw_code"] is None
    assert admin_detail.json()["can_reveal_code"] is False

    assert super_admin_detail.status_code == 200
    assert super_admin_detail.json()["raw_code"] == "SECRET30"
    assert super_admin_detail.json()["can_reveal_code"] is True

    async with SessionLocal.begin() as session:
        admin_audit_rows = (
            await session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "promo_reveal_code",
                    AdminAuditLog.target_id == str(promo_id),
                )
            )
        ).scalars().all()
        promo_audit_rows = (
            await session.execute(
                select(PromoAuditLog).where(
                    PromoAuditLog.action == "REVEAL_CODE",
                    PromoAuditLog.promo_code_id == promo_id,
                )
            )
        ).scalars().all()
        promo = await session.get(PromoCode, promo_id)
        assert promo is not None
        assert promo.code_encrypted is not None
        assert decrypt_promo_code(promo.code_encrypted) == "SECRET30"

    assert len(admin_audit_rows) == 1
    assert len(promo_audit_rows) == 1
