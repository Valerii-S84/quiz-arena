from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.models.purchases import Purchase
from app.db.session import SessionLocal
from app.economy.purchases.errors import StreakSaverPurchaseLimitError
from app.economy.purchases.service import PurchaseService
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_streak_saver_is_blocked_within_7_day_window() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user("streak-saver-limit")

    async with SessionLocal.begin() as session:
        first = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="STREAK_SAVER_20",
            idempotency_key="buy:streak-saver:1",
            now_utc=now_utc,
        )
        await PurchaseService.mark_invoice_sent(session, purchase_id=first.purchase_id)
        await PurchaseService.validate_precheckout(
            session,
            user_id=user_id,
            invoice_payload=first.invoice_payload,
            total_amount=20,
            now_utc=now_utc,
        )
        await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=first.invoice_payload,
            telegram_payment_charge_id="tg_charge_streak_saver_1",
            raw_successful_payment={"invoice_payload": first.invoice_payload},
            now_utc=now_utc,
        )

    with pytest.raises(StreakSaverPurchaseLimitError):
        async with SessionLocal.begin() as session:
            await PurchaseService.init_purchase(
                session,
                user_id=user_id,
                product_code="STREAK_SAVER_20",
                idempotency_key="buy:streak-saver:2",
                now_utc=now_utc + timedelta(days=6, hours=23),
            )

    async with SessionLocal.begin() as session:
        count_stmt = select(func.count(Purchase.id)).where(
            Purchase.user_id == user_id,
            Purchase.product_code == "STREAK_SAVER_20",
        )
        purchase_count = await session.scalar(count_stmt)
        assert purchase_count == 1


@pytest.mark.asyncio
async def test_streak_saver_is_allowed_after_7_days() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user("streak-saver-allowed")

    async with SessionLocal.begin() as session:
        first = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="STREAK_SAVER_20",
            idempotency_key="buy:streak-saver:3",
            now_utc=now_utc,
        )
        await PurchaseService.mark_invoice_sent(session, purchase_id=first.purchase_id)
        await PurchaseService.validate_precheckout(
            session,
            user_id=user_id,
            invoice_payload=first.invoice_payload,
            total_amount=20,
            now_utc=now_utc,
        )
        await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=first.invoice_payload,
            telegram_payment_charge_id="tg_charge_streak_saver_2",
            raw_successful_payment={"invoice_payload": first.invoice_payload},
            now_utc=now_utc,
        )

    async with SessionLocal.begin() as session:
        second = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="STREAK_SAVER_20",
            idempotency_key="buy:streak-saver:4",
            now_utc=now_utc + timedelta(days=7),
        )
        assert second.idempotent_replay is False
        assert second.purchase_id != first.purchase_id

    async with SessionLocal.begin() as session:
        count_stmt = select(func.count(Purchase.id)).where(
            Purchase.user_id == user_id,
            Purchase.product_code == "STREAK_SAVER_20",
        )
        purchase_count = await session.scalar(count_stmt)
        assert purchase_count == 2
