from __future__ import annotations

from datetime import datetime
from typing import cast

import pytest
from aiogram.types import InlineKeyboardMarkup
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.bot.texts.de import TEXTS_DE
from app.db.models.entitlements import Entitlement
from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase
from app.db.models.users import User
from app.db.session import SessionLocal
from app.main import app
from tests.integration.telegram_sandbox_smoke_bot import _BotApiStub, _configure_webhook_processing
from tests.integration.telegram_sandbox_smoke_fixtures import (
    UTC,
    _callback_update,
    _create_discount_promo_code,
    _message_update,
    _post_webhook_update,
    _precheckout_update,
)


@pytest.mark.asyncio
async def test_telegram_webhook_ignores_stale_promo_reply_without_waiting_state(
    monkeypatch,
) -> None:
    bot_api = _BotApiStub()
    queue = _configure_webhook_processing(monkeypatch, bot_api)
    telegram_user_id = 90_000_000_011

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        await _post_webhook_update(
            client,
            _message_update(
                update_id=1_000_011,
                telegram_user_id=telegram_user_id,
                message_id=111,
                text="WILLKOMMEN-50",
                reply_to_text=TEXTS_DE["msg.promo.input.hint"],
            ),
        )
        await queue.drain()

    assert bot_api.sent_messages == []

    async with SessionLocal.begin() as session:
        user = await session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
        assert user is None


@pytest.mark.asyncio
async def test_telegram_webhook_promo_button_state_accepts_plain_text_once(
    monkeypatch,
) -> None:
    now_utc = datetime.now(UTC)
    await _create_discount_promo_code(
        raw_code="STATE-50",
        discount_percent=50,
        target_scope="PREMIUM_MONTH",
        now_utc=now_utc,
    )
    bot_api = _BotApiStub()
    queue = _configure_webhook_processing(monkeypatch, bot_api)
    telegram_user_id = 90_000_000_012

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        await _post_webhook_update(
            client,
            _callback_update(
                update_id=1_000_012,
                telegram_user_id=telegram_user_id,
                callback_query_id="cb-smoke-shop-open-1",
                data="shop:open",
            ),
        )
        await queue.drain()

        shop_message = bot_api.sent_messages[-1]
        shop_markup = cast(InlineKeyboardMarkup, shop_message["reply_markup"])
        promo_callback_data = next(
            button.callback_data
            for row in shop_markup.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("promo:open:")
        )

        await _post_webhook_update(
            client,
            _callback_update(
                update_id=1_000_013,
                telegram_user_id=telegram_user_id,
                callback_query_id="cb-smoke-promo-open-1",
                data=promo_callback_data,
                message_id=cast(int, shop_message["message_id"]),
                message_text=str(shop_message["text"]),
            ),
        )
        await queue.drain()

        assert bot_api.sent_messages[-1]["text"] == TEXTS_DE["msg.promo.input.hint"]

        await _post_webhook_update(
            client,
            _message_update(
                update_id=1_000_014,
                telegram_user_id=telegram_user_id,
                message_id=113,
                text="STATE-50",
            ),
        )
        await queue.drain()
        sent_after_redeem = len(bot_api.sent_messages)

        await _post_webhook_update(
            client,
            _message_update(
                update_id=1_000_015,
                telegram_user_id=telegram_user_id,
                message_id=114,
                text="STATE-50",
            ),
        )
        await queue.drain()

    assert bot_api.sent_messages[2]["text"] == TEXTS_DE["msg.promo.success.discount"]
    assert len(bot_api.sent_messages) == sent_after_redeem

    async with SessionLocal.begin() as session:
        user = await session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
        assert user is not None
        redemption_count = await session.scalar(
            select(func.count(PromoRedemption.id)).where(PromoRedemption.user_id == user.id)
        )
        assert int(redemption_count or 0) == 1


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
