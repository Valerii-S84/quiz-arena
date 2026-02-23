from __future__ import annotations

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db.models.entitlements import Entitlement
from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase
from app.db.models.users import User
from app.db.session import SessionLocal
from app.main import app
from tests.integration.telegram_sandbox_smoke_fixtures import (
    UTC,
    _BotApiStub,
    _callback_update,
    _configure_webhook_processing,
    _create_discount_promo_code,
    _message_update,
    _post_webhook_update,
    _precheckout_update,
)


@pytest.mark.asyncio
async def test_telegram_webhook_smoke_promo_discount_purchase_flow(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
    promo_code = await _create_discount_promo_code(
        raw_code="WILLKOMMEN-50",
        discount_percent=50,
        target_scope="PREMIUM_MONTH",
        now_utc=now_utc,
    )
    bot_api = _BotApiStub()
    queue = _configure_webhook_processing(monkeypatch, bot_api)

    telegram_user_id = 90_000_000_001

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        await _post_webhook_update(
            client,
            _message_update(
                update_id=1_000_001,
                telegram_user_id=telegram_user_id,
                message_id=101,
                text="/promo WILLKOMMEN-50",
            ),
        )
        await queue.drain()

        async with SessionLocal.begin() as session:
            user = await session.scalar(
                select(User).where(User.telegram_user_id == telegram_user_id)
            )
            assert user is not None
            redemption = await session.scalar(
                select(PromoRedemption)
                .where(PromoRedemption.user_id == user.id)
                .order_by(PromoRedemption.created_at.desc())
                .limit(1)
            )
            assert redemption is not None
            assert redemption.status == "RESERVED"
            redemption_id = redemption.id
            user_id = user.id

        await _post_webhook_update(
            client,
            _callback_update(
                update_id=1_000_002,
                telegram_user_id=telegram_user_id,
                callback_query_id="cb-smoke-buy-1",
                data=f"buy:PREMIUM_MONTH:promo:{redemption_id}",
            ),
        )
        await queue.drain()

        assert len(bot_api.sent_invoices) == 1
        invoice = bot_api.sent_invoices[0]
        assert invoice["total_amount"] == 50
        invoice_payload = str(invoice["invoice_payload"])

        await _post_webhook_update(
            client,
            _precheckout_update(
                update_id=1_000_003,
                telegram_user_id=telegram_user_id,
                precheckout_id="pc-smoke-1",
                invoice_payload=invoice_payload,
                total_amount=50,
            ),
        )
        await queue.drain()
        assert bot_api.precheckout_answers[-1]["ok"] is True

        await _post_webhook_update(
            client,
            _message_update(
                update_id=1_000_004,
                telegram_user_id=telegram_user_id,
                message_id=102,
                successful_payment={
                    "currency": "XTR",
                    "total_amount": 50,
                    "invoice_payload": invoice_payload,
                    "telegram_payment_charge_id": "tg_smoke_promo_discount_1",
                    "provider_payment_charge_id": "provider_smoke_1",
                },
            ),
        )
        await queue.drain()

    async with SessionLocal.begin() as session:
        purchase = await session.scalar(
            select(Purchase).where(Purchase.invoice_payload == invoice_payload)
        )
        assert purchase is not None
        assert purchase.user_id == user_id
        assert purchase.status == "CREDITED"
        assert purchase.product_code == "PREMIUM_MONTH"
        assert purchase.base_stars_amount == 99
        assert purchase.discount_stars_amount == 49
        assert purchase.stars_amount == 50
        assert purchase.applied_promo_code_id == promo_code.id

        redemption = await session.get(PromoRedemption, redemption_id)
        assert redemption is not None
        assert redemption.status == "APPLIED"
        assert redemption.applied_purchase_id == purchase.id

        active_premium = await session.scalar(
            select(func.count(Entitlement.id)).where(
                Entitlement.user_id == user_id,
                Entitlement.entitlement_type == "PREMIUM",
                Entitlement.scope == "PREMIUM_MONTH",
                Entitlement.status == "ACTIVE",
            )
        )
        assert int(active_premium or 0) == 1
