from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.promo_audit_log import PromoAuditLog
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.main import app
from app.services.admin.auth import build_access_token
from app.services.promo_codes import hash_promo_code, normalize_promo_code
from app.services.promo_encryption import encrypt_promo_code

UTC = timezone.utc


def _admin_headers(*, role: str) -> dict[str, str]:
    token = build_access_token(
        settings=get_settings(),
        email="admin@example.com",
        role=role,
        two_factor_verified=True,
    )
    return {"Authorization": f"Bearer {token}"}


async def _create_user(seed: str) -> int:
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


async def _redeem_code(*, user_id: int, promo_code: str, suffix: str) -> None:
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


async def _create_discount_promo_via_api(*, code: str = "WELCOME50") -> dict[str, object]:
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
            headers=_admin_headers(role="admin"),
        )
    assert response.status_code == 200
    return response.json()


async def _insert_promo(*, promo_id: int, raw_code: str, now_utc: datetime) -> None:
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


@pytest.mark.asyncio
async def test_admin_promo_patch_updates_fields() -> None:
    created = await _create_discount_promo_via_api(code="PATCHME50")
    promo_id = int(created["id"])

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        patch_response = await client.patch(
            f"/admin/promo/{promo_id}",
            json={
                "campaign_name": "Sommer Finale",
                "discount_type": "FIXED",
                "discount_value": 7,
                "applicable_products": ["ENERGY_10", "PREMIUM_MONTH"],
                "valid_until": "2026-12-31T10:00:00+00:00",
                "max_total_uses": 0,
                "max_per_user": 3,
            },
            headers=_admin_headers(role="admin"),
        )

    assert patch_response.status_code == 200
    payload = patch_response.json()
    assert payload["campaign_name"] == "Sommer Finale"
    assert payload["discount_type"] == "FIXED"
    assert payload["discount_value"] == 7
    assert payload["applicable_products"] == ["ENERGY_10", "PREMIUM_MONTH"]
    assert payload["max_total_uses"] == 0
    assert payload["max_per_user"] == 3

    async with SessionLocal.begin() as session:
        promo = await session.get(PromoCode, promo_id)
        assert promo is not None
        assert promo.discount_type == "FIXED"
        assert promo.discount_value == 7
        assert promo.discount_percent is None
        assert promo.applicable_products == ["ENERGY_10", "PREMIUM_MONTH"]
        assert promo.max_total_uses is None
        assert promo.max_uses_per_user == 3

        audit_rows = (
            await session.execute(
                select(PromoAuditLog).where(
                    PromoAuditLog.action == "UPDATE",
                    PromoAuditLog.promo_code_id == promo_id,
                )
            )
        ).scalars().all()
    assert len(audit_rows) == 1


@pytest.mark.asyncio
async def test_admin_promo_bulk_generate_100() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/admin/promo/bulk-generate",
            json={
                "count": 100,
                "prefix": "mass",
                "campaign_name": "Massenversand",
                "discount_type": "PERCENT",
                "discount_value": 30,
                "applicable_products": ["ENERGY_10"],
                "max_total_uses": 1,
                "max_per_user": 1,
            },
            headers=_admin_headers(role="admin"),
        )

    assert response.status_code == 200
    payload = response.json()
    codes = payload["codes"]
    assert payload["generated"] == 100
    assert len(codes) == 100
    assert len(set(codes)) == 100
    assert all(code.startswith("MASS") for code in codes)

    users = [await _create_user(f"bulk-{idx}") for idx in range(100)]
    for idx, (user_id, raw_code) in enumerate(zip(users, codes, strict=True)):
        await _redeem_code(user_id=user_id, promo_code=raw_code, suffix=f"bulk-{idx}")

    async with SessionLocal.begin() as session:
        promos = (await session.execute(select(PromoCode))).scalars().all()
    assert len(promos) == 100
    assert all(promo.code_encrypted is not None for promo in promos)


@pytest.mark.asyncio
async def test_admin_promo_bulk_generate_collision(monkeypatch: pytest.MonkeyPatch) -> None:
    now_utc = datetime.now(UTC)
    await _insert_promo(promo_id=990_001, raw_code="MASSAAAA1111", now_utc=now_utc)
    sequence = [
        ["MASSAAAA1111", "MASSBBBB2222"],
        ["MASSCCCC3333"],
    ]

    def _fake_generator(*, prefix: str | None, count: int) -> list[str]:
        assert count >= 1
        return sequence.pop(0)

    monkeypatch.setattr("app.api.routes.admin.promo_writes.build_generated_codes", _fake_generator)

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/admin/promo/bulk-generate",
            json={
                "count": 2,
                "prefix": "mass",
                "campaign_name": "Kollision",
                "discount_type": "PERCENT",
                "discount_value": 10,
                "max_total_uses": 1,
                "max_per_user": 1,
            },
            headers=_admin_headers(role="admin"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["generated"] == 2
    assert payload["codes"] == ["MASSBBBB2222", "MASSCCCC3333"]


@pytest.mark.asyncio
async def test_admin_promo_stats_endpoint() -> None:
    user_reserved = await _create_user("stats-reserved")
    user_applied = await _create_user("stats-applied")
    now_utc = datetime.now(UTC)
    promo_id = 990_100
    purchase_id = uuid4()

    await _insert_promo(promo_id=promo_id, raw_code="STATS5000", now_utc=now_utc)
    async with SessionLocal.begin() as session:
        promo = await session.get(PromoCode, promo_id)
        assert promo is not None
        promo.used_total = 1
        session.add(
            Purchase(
                id=purchase_id,
                user_id=user_applied,
                product_code="ENERGY_10",
                product_type="MICRO",
                base_stars_amount=5,
                discount_stars_amount=1,
                stars_amount=4,
                currency="XTR",
                status="CREDITED",
                applied_promo_code_id=promo_id,
                idempotency_key=f"stats-purchase:{purchase_id}",
                invoice_payload=f"stats-invoice:{purchase_id}",
                telegram_payment_charge_id="tg_stats_paid",
                telegram_pre_checkout_query_id="pre_stats_paid",
                raw_successful_payment={"ok": True},
                created_at=now_utc - timedelta(hours=1),
                paid_at=now_utc - timedelta(hours=1),
                credited_at=now_utc - timedelta(minutes=50),
                refunded_at=None,
            )
        )
        await session.flush()
        session.add_all(
            [
                PromoRedemption(
                    id=uuid4(),
                    promo_code_id=promo_id,
                    user_id=user_reserved,
                    status="RESERVED",
                    reject_reason=None,
                    reserved_until=now_utc + timedelta(minutes=10),
                    applied_purchase_id=None,
                    grant_entitlement_id=None,
                    idempotency_key="stats-reserved",
                    validation_snapshot={},
                    created_at=now_utc - timedelta(minutes=20),
                    applied_at=None,
                    updated_at=now_utc - timedelta(minutes=20),
                ),
                PromoRedemption(
                    id=uuid4(),
                    promo_code_id=promo_id,
                    user_id=user_applied,
                    status="APPLIED",
                    reject_reason=None,
                    reserved_until=None,
                    applied_purchase_id=purchase_id,
                    grant_entitlement_id=None,
                    idempotency_key="stats-applied",
                    validation_snapshot={},
                    created_at=now_utc - timedelta(hours=1),
                    applied_at=now_utc - timedelta(minutes=50),
                    updated_at=now_utc - timedelta(minutes=50),
                ),
            ]
        )

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/admin/promo/{promo_id}/stats",
            headers=_admin_headers(role="admin"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["used_total"] == 1
    assert payload["reserved_active"] == 1
    assert payload["status_totals"]["APPLIED"] == 1
    assert payload["status_totals"]["RESERVED"] == 1
    assert len(payload["redemptions"]) == 2
    assert {item["status"] for item in payload["redemptions"]} == {"RESERVED", "APPLIED"}
    assert {item["product_id"] for item in payload["redemptions"]} == {None, "ENERGY_10"}


@pytest.mark.asyncio
async def test_admin_promo_audit_log_written() -> None:
    user_id = await _create_user("audit-user")
    created = await _create_discount_promo_via_api(code="AUDIT501")
    promo_id = int(created["id"])
    raw_code = str(created["raw_code"])
    await _redeem_code(user_id=user_id, promo_code=raw_code, suffix="audit")

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        toggle_response = await client.patch(
            f"/admin/promo/{promo_id}/toggle",
            headers=_admin_headers(role="admin"),
        )
        revoke_response = await client.post(
            f"/admin/promo/{promo_id}/revoke",
            json={"reason": "Missbrauch"},
            headers=_admin_headers(role="admin"),
        )

    assert toggle_response.status_code == 200
    assert revoke_response.status_code == 200
    assert revoke_response.json()["revoked_count"] == 1

    async with SessionLocal.begin() as session:
        audit_rows = (
            await session.execute(
                select(PromoAuditLog).where(PromoAuditLog.promo_code_id == promo_id)
            )
        ).scalars().all()
    assert {"CREATE", "DEACTIVATE", "REVOKE"} <= {row.action for row in audit_rows}
    assert next(row for row in audit_rows if row.action == "REVOKE").details["reason"] == "Missbrauch"


@pytest.mark.asyncio
async def test_admin_promo_check_code_reports_existing_and_available() -> None:
    created = await _create_discount_promo_via_api(code="CHECK500")

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        existing_response = await client.get(
            "/admin/promo/check-code",
            params={"code": "check500"},
            headers=_admin_headers(role="admin"),
        )
        available_response = await client.get(
            "/admin/promo/check-code",
            params={"code": "fresh500"},
            headers=_admin_headers(role="admin"),
        )

    assert created["raw_code"] == "CHECK500"
    assert existing_response.status_code == 200
    assert existing_response.json() == {"normalized_code": "CHECK500", "exists": True}
    assert available_response.status_code == 200
    assert available_response.json() == {"normalized_code": "FRESH500", "exists": False}
