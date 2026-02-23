from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.db.models.promo_codes import PromoCode
from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase
from app.db.repo.promo_repo import PromoRepo
from app.db.session import SessionLocal
from app.workers.tasks.payments_reliability import run_refund_promo_rollback_async
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_refund_promo_rollback_job_revokes_discount_redemption_without_decrementing_usage() -> (
    None
):
    now_utc = datetime.now(UTC)
    user_id = await _create_user("refund-promo-rollback")
    purchase_id = uuid4()
    redemption_id = uuid4()
    promo_code_id = 91_002

    async with SessionLocal.begin() as session:
        session.add(
            PromoCode(
                id=promo_code_id,
                code_hash=uuid4().hex + uuid4().hex,
                code_prefix="ROLLBACK",
                campaign_name="refund-rollback",
                promo_type="PERCENT_DISCOUNT",
                grant_premium_days=None,
                discount_percent=50,
                target_scope="PREMIUM_MONTH",
                status="ACTIVE",
                valid_from=now_utc - timedelta(days=1),
                valid_until=now_utc + timedelta(days=1),
                max_total_uses=100,
                used_total=1,
                max_uses_per_user=1,
                new_users_only=False,
                first_purchase_only=False,
                created_by="integration-test",
                created_at=now_utc - timedelta(days=1),
                updated_at=now_utc - timedelta(hours=2),
            )
        )
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
                status="REFUNDED",
                applied_promo_code_id=promo_code_id,
                idempotency_key=f"refund-promo-rollback:{purchase_id}",
                invoice_payload=f"refund-promo-rollback:{purchase_id}",
                telegram_payment_charge_id="tg_charge_refund_rollback_1",
                telegram_pre_checkout_query_id="pre_checkout_refund_rollback_1",
                raw_successful_payment={"ok": True},
                created_at=now_utc - timedelta(hours=4),
                paid_at=now_utc - timedelta(hours=4),
                credited_at=now_utc - timedelta(hours=3),
                refunded_at=now_utc - timedelta(hours=1),
            )
        )
        await session.flush()
        session.add(
            PromoRedemption(
                id=redemption_id,
                promo_code_id=promo_code_id,
                user_id=user_id,
                status="APPLIED",
                reject_reason=None,
                reserved_until=now_utc - timedelta(hours=2),
                applied_purchase_id=purchase_id,
                grant_entitlement_id=None,
                idempotency_key=f"refund-promo-rollback-redemption:{redemption_id}",
                validation_snapshot={"promo_type": "PERCENT_DISCOUNT"},
                created_at=now_utc - timedelta(hours=4),
                applied_at=now_utc - timedelta(hours=3),
                updated_at=now_utc - timedelta(hours=3),
            )
        )
        await session.flush()

    first = await run_refund_promo_rollback_async(batch_size=50)
    second = await run_refund_promo_rollback_async(batch_size=50)

    assert first["examined"] == 1
    assert first["rolled_back"] == 1
    assert first["errors"] == 0
    assert second["examined"] == 0
    assert second["rolled_back"] == 0

    async with SessionLocal.begin() as session:
        redemption = await PromoRepo.get_redemption_by_id(session, redemption_id)
        assert redemption is not None
        assert redemption.status == "REVOKED"

        promo_code = await PromoRepo.get_code_by_id(session, promo_code_id)
        assert promo_code is not None
        assert promo_code.used_total == 1
