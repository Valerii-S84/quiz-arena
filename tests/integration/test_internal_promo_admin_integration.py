from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.db.models.ledger_entries import LedgerEntry
from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.main import app
from app.services.promo_codes import hash_promo_code, normalize_promo_code

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=80_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"P{uuid4().hex[:10]}",
            username=None,
            first_name="PromoAdmin",
            referred_by_user_id=None,
        )
        return user.id


async def _create_discount_campaign(*, code_id: int, now_utc: datetime) -> PromoCode:
    raw_code = f"ADMIN-{code_id}"
    normalized = normalize_promo_code(raw_code)
    code_hash = hash_promo_code(
        normalized_code=normalized,
        pepper=get_settings().promo_secret_pepper,
    )
    promo_code = PromoCode(
        id=code_id,
        code_hash=code_hash,
        code_prefix=normalized[:8],
        campaign_name="admin-campaign",
        promo_type="PERCENT_DISCOUNT",
        grant_premium_days=None,
        discount_percent=50,
        target_scope="PREMIUM_MONTH",
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


async def _post_json(path: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            path,
            json=payload,
            headers={"X-Internal-Token": get_settings().internal_api_token},
        )
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_internal_promo_campaign_status_update_and_listing() -> None:
    now_utc = datetime.now(UTC)
    promo_code = await _create_discount_campaign(code_id=9001, now_utc=now_utc)

    status_code, payload = await _post_json(
        f"/internal/promo/campaigns/{promo_code.id}/status",
        {
            "status": "PAUSED",
            "reason": "manual triage",
            "expected_current_status": "ACTIVE",
        },
    )

    assert status_code == 200
    assert payload["id"] == promo_code.id
    assert payload["status"] == "PAUSED"

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        list_response = await client.get(
            "/internal/promo/campaigns?status=PAUSED",
            headers={"X-Internal-Token": get_settings().internal_api_token},
        )

    assert list_response.status_code == 200
    list_payload = list_response.json()
    ids = [int(item["id"]) for item in list_payload["campaigns"]]
    assert promo_code.id in ids


@pytest.mark.asyncio
async def test_internal_promo_campaign_status_rejects_unpause_from_depleted() -> None:
    now_utc = datetime.now(UTC)
    promo_code = await _create_discount_campaign(code_id=9003, now_utc=now_utc)
    async with SessionLocal.begin() as session:
        db_promo_code = await session.get(PromoCode, promo_code.id)
        assert db_promo_code is not None
        db_promo_code.status = "DEPLETED"
        db_promo_code.updated_at = now_utc - timedelta(minutes=5)

    status_code, payload = await _post_json(
        f"/internal/promo/campaigns/{promo_code.id}/status",
        {
            "status": "ACTIVE",
            "reason": "unsafe unpause attempt",
            "expected_current_status": "DEPLETED",
        },
    )

    assert status_code == 409
    assert payload == {"detail": {"code": "E_PROMO_STATUS_CONFLICT"}}


@pytest.mark.asyncio
async def test_internal_promo_refund_rollback_revokes_redemption_and_is_idempotent() -> None:
    now_utc = datetime.now(UTC)
    user_id = await _create_user("promo-admin-refund")
    promo_code = await _create_discount_campaign(code_id=9002, now_utc=now_utc)

    purchase_id = uuid4()
    redemption_id = uuid4()
    async with SessionLocal.begin() as session:
        db_promo_code = await session.get(PromoCode, promo_code.id)
        assert db_promo_code is not None
        db_promo_code.used_total = 1
        session.add(
            Purchase(
                id=purchase_id,
                user_id=user_id,
                product_code="PREMIUM_MONTH",
                product_type="PREMIUM",
                base_stars_amount=50,
                discount_stars_amount=25,
                stars_amount=25,
                currency="XTR",
                status="CREDITED",
                applied_promo_code_id=promo_code.id,
                idempotency_key=f"promo-admin-purchase:{purchase_id}",
                invoice_payload=f"promo-admin-invoice:{purchase_id}",
                telegram_payment_charge_id="tg_charge_admin_refund_1",
                telegram_pre_checkout_query_id="pre_checkout_admin_refund_1",
                raw_successful_payment={"ok": True},
                created_at=now_utc - timedelta(hours=2),
                paid_at=now_utc - timedelta(hours=2),
                credited_at=now_utc - timedelta(hours=1),
                refunded_at=None,
            )
        )
        session.add(
            LedgerEntry(
                user_id=user_id,
                purchase_id=purchase_id,
                entry_type="PURCHASE_CREDIT",
                asset="PURCHASE",
                direction="CREDIT",
                amount=25,
                balance_after=None,
                source="PURCHASE",
                idempotency_key=f"credit:purchase:{purchase_id}",
                metadata_={
                    "product_code": "PREMIUM_MONTH",
                    "asset_breakdown": {"premium_days": 30},
                },
                created_at=now_utc - timedelta(hours=1),
            )
        )
        await session.flush()
        session.add(
            PromoRedemption(
                id=redemption_id,
                promo_code_id=promo_code.id,
                user_id=user_id,
                status="APPLIED",
                reject_reason=None,
                reserved_until=now_utc + timedelta(minutes=5),
                applied_purchase_id=purchase_id,
                grant_entitlement_id=None,
                idempotency_key=f"promo-admin-redemption:{redemption_id}",
                validation_snapshot={"promo_type": "PERCENT_DISCOUNT"},
                created_at=now_utc - timedelta(hours=2),
                applied_at=now_utc - timedelta(hours=1),
                updated_at=now_utc - timedelta(hours=1),
            )
        )

    first_status, first_payload = await _post_json(
        "/internal/promo/refund-rollback",
        {
            "purchase_id": str(purchase_id),
            "reason": "provider_refund",
        },
    )
    second_status, second_payload = await _post_json(
        "/internal/promo/refund-rollback",
        {
            "purchase_id": str(purchase_id),
            "reason": "provider_refund_duplicate",
        },
    )

    assert first_status == 200
    assert first_payload["purchase_status"] == "REFUNDED"
    assert first_payload["promo_redemption_id"] == str(redemption_id)
    assert first_payload["promo_redemption_status"] == "REVOKED"
    assert first_payload["promo_code_id"] == promo_code.id
    assert first_payload["promo_code_used_total"] == 1
    assert first_payload["idempotent_replay"] is False

    assert second_status == 200
    assert second_payload["purchase_status"] == "REFUNDED"
    assert second_payload["promo_redemption_status"] == "REVOKED"
    assert second_payload["promo_code_used_total"] == 1
    assert second_payload["idempotent_replay"] is True
